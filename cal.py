import base64
import io
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode

from app.auth import migrate_legacy_password, validate_email, verify_password, hash_password
from app.constants import ACTIVITY_LEVELS, EXERCISE_METS, GOALS, MEALS
from app.db import load_db, sync_db
from app.models import default_user, ensure_user_schema
from app.services import (
    calculate_targets,
    generate_sms_alert,
    load_fitness_db,
    robust_global_search,
    send_real_sms_mock,
    suggest_meal,
    translate_query,
)

st.set_page_config(page_title="MyFitness Pro", page_icon="🍏", layout="centered")

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Heebo', sans-serif; }
    .app-title { text-align: center; color: #1e293b; font-weight: 800; font-size: 2.2rem; margin-bottom: 5px; }
    .app-subtitle { text-align: center; color: #64748b; font-size: 1rem; margin-top: 0px; margin-bottom: 25px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: none; justify-content: center; }
    .stTabs [data-baseweb="tab"] { border-radius: 12px; padding: 10px 16px; color: #64748b; font-weight: 500; background-color: #f1f5f9; border: none; }
    .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; font-weight: 700; box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3); }
    div[data-testid="stMetric"] { background-color: #ffffff; padding: 15px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #f1f5f9; text-align: center; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #0f172a; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem; font-weight: 600; color: #64748b; margin-bottom: 5px; }
    [data-testid="stExpander"] { border-radius: 16px !important; border: 1px solid #e2e8f0 !important; }
    header {visibility: hidden;} footer {visibility: hidden;} [data-testid="stToolbar"] {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)


def init_state():
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("auth_mode", "Login")
    st.session_state.setdefault("camera_active", False)


def get_day_data(user_data, selected_day: str):
    daily = user_data.get("daily_logs_by_date", {}).get(selected_day, [])
    ex = user_data.get("exercise_logs_by_date", {}).get(selected_day, [])
    water = user_data.get("water_by_date", {}).get(selected_day, user_data.get("water_liters", 0.0))
    return daily, ex, water


def set_day_data(user_data, selected_day: str, daily_log, ex_log, water_liters: float):
    user_data.setdefault("daily_logs_by_date", {})[selected_day] = daily_log
    user_data.setdefault("exercise_logs_by_date", {})[selected_day] = ex_log
    user_data.setdefault("water_by_date", {})[selected_day] = water_liters
    if selected_day == str(date.today()):
        user_data["daily_log"] = daily_log
        user_data["exercise_log"] = ex_log
        user_data["water_liters"] = water_liters


def auth_screen(db):
    st.markdown("<h1 class='app-title'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Your Personal Nutrition & Training App</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### 👋 Welcome Back")
                with st.form("login_form"):
                    le = st.text_input("📧 Email").lower().strip()
                    lp = st.text_input("🔒 Password", type="password")
                    remember = st.checkbox("💾 Remember Me", value=True)
                    submit_btn = st.form_submit_button("Log In", type="primary", use_container_width=True)
                    if submit_btn:
                        if le in db["users"] and verify_password(db["users"][le], lp):
                            changed = migrate_legacy_password(db["users"][le])
                            if changed:
                                sync_db(db)
                            st.session_state.logged_in = True
                            st.session_state.current_user = le
                            if remember:
                                st.query_params["user"] = le
                            st.rerun()
                        st.error("Wrong email or password.")
                if st.button("New here? Create Account", use_container_width=True):
                    st.session_state.auth_mode = "Register"
                    st.rerun()

            elif st.session_state.auth_mode == "Register":
                st.markdown("### ✨ Create Account")
                with st.form("register_form"):
                    re = st.text_input("📧 Email").lower().strip()
                    rp = st.text_input("🔒 Password", type="password")
                    reg_btn = st.form_submit_button("Get Started", type="primary", use_container_width=True)
                    if reg_btn:
                        if not validate_email(re):
                            st.error("Please enter a valid email address.")
                        elif len(rp) < 6:
                            st.error("Password must be at least 6 characters.")
                        elif re in db["users"]:
                            st.error("Account exists!")
                        else:
                            st.session_state.temp_reg = {"e": re, "p": rp}
                            st.session_state.auth_mode = "Verify"
                            st.rerun()
                if st.button("⬅️ Back to Login"):
                    st.session_state.auth_mode = "Login"
                    st.rerun()

            else:
                st.info("💡 Hint: Enter '1234' to verify")
                with st.form("verify_form"):
                    vc = st.text_input("Enter 4-digit code")
                    v_btn = st.form_submit_button("Verify Account", type="primary", use_container_width=True)
                    if v_btn and vc == "1234":
                        email = st.session_state.temp_reg["e"]
                        db["users"][email] = default_user(email, hash_password(st.session_state.temp_reg["p"]))
                        sync_db(db)
                        st.session_state.logged_in = True
                        st.session_state.current_user = email
                        st.query_params["user"] = email
                        st.rerun()


def onboarding(user_data, db):
    st.markdown("<h2 style='text-align: center;'>🎯 Let's build your plan</h2>", unsafe_allow_html=True)
    with st.container(border=True):
        col1, col2 = st.columns(2)
        gen = col1.selectbox("🚻 Gender", ["Male", "Female"])
        age = col2.number_input("🎂 Age", min_value=10, value=21)
        weight = col1.number_input("⚖️ Weight (kg)", min_value=30.0, value=75.0)
        height = col2.number_input("📏 Height (cm)", min_value=100.0, value=175.0)
        act = st.selectbox("🏃‍♂️ Activity Level", ACTIVITY_LEVELS)
        goal = st.selectbox("🎯 Your Goal", GOALS)
        if st.button("🚀 Calculate My Plan", type="primary", use_container_width=True):
            cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
            user_data.update(
                {
                    "profile": {
                        "gender": gen,
                        "age": age,
                        "height": height,
                        "activity": act,
                        "goal": goal,
                        "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water},
                    },
                    "weight_log": [{"Date": str(date.today()), "Weight": weight}],
                    "onboarding_done": True,
                }
            )
            set_day_data(user_data, str(date.today()), [], [], 0.0)
            sync_db(db)
            st.rerun()


def main_app(db):
    user_data = db["users"][st.session_state.current_user]
    ensure_user_schema(user_data)

    if not user_data.get("onboarding_done", False):
        onboarding(user_data, db)
        return

    profile = user_data["profile"]
    targets = profile["targets"]
    w_log = user_data.get("weight_log", [])
    current_weight = sorted(w_log, key=lambda x: x["Date"])[-1]["Weight"] if w_log else 75.0
    selected_day = st.sidebar.date_input("📅 Active day", value=date.today()).isoformat()
    daily_log, exercise_log, water_liters = get_day_data(user_data, selected_day)

    with st.sidebar:
        c1, c2 = st.columns([1, 2.5])
        pic_b64 = user_data.get("profile_pic", "")
        with c1:
            if pic_b64:
                st.markdown(
                    f'<img src="data:image/jpeg;base64,{pic_b64}" style="width:65px; height:65px; border-radius:50%; object-fit:cover; border:2px solid #3b82f6;">',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("<div style='font-size: 55px;'>👤</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<h3 style='margin-bottom:0px; padding-top:10px;'>{user_data.get('username')}</h3>", unsafe_allow_html=True)
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.logged_in = False
                st.query_params.clear()
                st.rerun()
        st.divider()

        with st.expander("📝 Account & Alerts"):
            old_phone = user_data.get("phone", "")
            old_sms = user_data.get("sms_alerts", False)
            new_username = st.text_input("Username", value=user_data.get("username"))
            new_phone = st.text_input("📱 Phone (For Alerts)", value=old_phone, placeholder="e.g. 0501234567")
            sms_toggle = st.checkbox("🔔 Enable SMS Reminders", value=old_sms)
            new_pic = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png"])

            if st.button("💾 Save Settings", use_container_width=True):
                taken = any(u.get("username") == new_username for k, u in db["users"].items() if k != st.session_state.current_user)
                if taken:
                    st.error("Username is taken!")
                else:
                    user_data["username"] = new_username
                    user_data["phone"] = new_phone
                    user_data["sms_alerts"] = sms_toggle
                    if new_pic:
                        img = Image.open(new_pic).convert("RGB")
                        img.thumbnail((150, 150))
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG")
                        user_data["profile_pic"] = base64.b64encode(buffered.getvalue()).decode()
                    if sms_toggle and (new_phone != old_phone or not old_sms) and new_phone:
                        send_real_sms_mock(new_phone, "שלום! 🍏 ברוך הבא להתראות MyFitness Pro.")
                        st.toast(f"📲 נשלח SMS ברוך הבא למספר {new_phone}!")
                    sync_db(db)
                    st.success("Profile Saved!")
                    st.rerun()

        with st.expander("⚖️ Edit Body Profile"):
            new_gen = st.selectbox("Gender", ["Male", "Female"], index=["Male", "Female"].index(profile.get("gender", "Male")))
            new_age = st.number_input("Age", value=int(profile.get("age", 21)), min_value=10)
            new_height = st.number_input("Height (cm)", value=int(profile.get("height", 175)), min_value=100)
            new_act = st.selectbox("Activity", ACTIVITY_LEVELS, index=ACTIVITY_LEVELS.index(profile["activity"]))
            new_goal = st.selectbox("Goal", GOALS, index=GOALS.index(profile["goal"]))
            if st.button("🔄 Recalculate Targets", use_container_width=True):
                c, p, cb, f, w = calculate_targets(new_gen, new_age, current_weight, new_height, new_act, new_goal)
                user_data["profile"].update(
                    {
                        "gender": new_gen,
                        "age": new_age,
                        "height": new_height,
                        "activity": new_act,
                        "goal": new_goal,
                        "targets": {"cals": c, "prot": p, "carb": cb, "fat": f, "water": w},
                    }
                )
                sync_db(db)
                st.success("Updated!")
                st.rerun()

        st.divider()
        st.markdown("### 💧 Hydration Station")
        user_water_goal = st.number_input("🎯 Goal (L)", value=float(targets.get("water", 2.5)), step=0.25)
        if user_water_goal != targets.get("water"):
            user_data["profile"]["targets"]["water"] = user_water_goal
            sync_db(db)

        w_c1, w_c2, w_c3 = st.columns([1, 1, 1])
        if w_c1.button("➖", use_container_width=True):
            water_liters = max(0.0, water_liters - 0.25)
            set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
            sync_db(db)
        w_c2.markdown(f"<h3 style='text-align:center; color:#3b82f6;'>{water_liters:.2f}L</h3>", unsafe_allow_html=True)
        if w_c3.button("➕", use_container_width=True):
            water_liters = water_liters + 0.25
            set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
            sync_db(db)
        st.progress(min(water_liters / user_water_goal, 1.0) if user_water_goal > 0 else 0)

    st.markdown("<h1 class='app-title'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
    t_dash, t_add, t_ex, t_weight, t_custom = st.tabs(["📊 Summary", "🍏 Add Food", "👟 Exercise", "📈 Weight", "👨‍🍳 Recipes"])

    with t_dash:
        df_f = pd.DataFrame(daily_log)
        if df_f.empty:
            df_f = pd.DataFrame(columns=["Meal", "Food", "Grams", "Calories", "Protein", "Carbs", "Fat"])
        df_e = pd.DataFrame(exercise_log)
        if df_e.empty:
            df_e = pd.DataFrame(columns=["Exercise", "Burned"])

        t_food, t_burn = df_f["Calories"].sum(), df_e["Burned"].sum()
        rem_c = targets["cals"] - (t_food - t_burn)
        rem_p = max(0, targets["prot"] - df_f["Protein"].sum())
        rem_w = max(0, targets["water"] - water_liters)

        if user_data.get("sms_alerts") and user_data.get("phone"):
            sms_text = generate_sms_alert(rem_c, rem_p, rem_w, profile.get("goal"))
            st.info(f"📱 **SMS Alerts Active ({user_data['phone']})**")
            with st.expander("📬 View Pending Alerts & Motivation"):
                st.write(sms_text)
                if st.button("🔔 Send Test SMS Now", type="secondary"):
                    send_real_sms_mock(user_data["phone"], sms_text)
                    st.toast("✅ SMS Sent successfully! (Simulation)")

        st.markdown("### 🔋 Energy Balance")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🎯 Goal", targets["cals"])
        m2.metric("🍔 Food", f"{t_food:.0f}")
        m3.metric("🔥 Burned", f"{t_burn:.0f}")
        m4.metric("📉 Left", f"{rem_c:.0f}" if rem_c >= 0 else f"⚠️ {abs(rem_c):.0f} Over")
        st.progress(min(max(0, (t_food - t_burn) / targets["cals"]), 1.0) if targets["cals"] > 0 else 0)

        st.caption(f"💡 {suggest_meal(rem_c, rem_p)}")

        col_ma, col_pi = st.columns([1.2, 1])
        with col_ma:
            st.markdown("### 🥩 Macros")
            for m, cur, goal, color, icon in [
                ("Protein", df_f["Protein"].sum(), targets["prot"], "#ef4444", "🥩"),
                ("Carbs", df_f["Carbs"].sum(), targets["carb"], "#3b82f6", "🍞"),
                ("Fat", df_f["Fat"].sum(), targets["fat"], "#10b981", "🥑"),
            ]:
                diff = goal - cur
                status = f"{diff:.0f}g left" if diff >= 0 else f"⚠️ Over {abs(diff):.0f}g"
                st.markdown(
                    f"**{icon} {m}:** {cur:.0f}g / {goal}g | <span style='color:{color if diff >= 0 else '#dc2626'}; font-weight:600;'>{status}</span>",
                    unsafe_allow_html=True,
                )
                st.progress(min(cur / goal, 1.0) if goal > 0 else 0)
        with col_pi:
            fig = px.pie(
                pd.DataFrame({"M": ["Pro", "Carb", "Fat"], "G": [df_f["Protein"].sum(), df_f["Carbs"].sum(), df_f["Fat"].sum()]}),
                values="G",
                names="M",
                hole=0.5,
                color_discrete_sequence=["#ef4444", "#3b82f6", "#10b981"],
            )
            fig.update_layout(height=180, showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("### 🍽️ Meals Diary")
        for meal in MEALS:
            m_data = df_f[df_f["Meal"] == meal]
            with st.expander(f"{meal} | {m_data['Calories'].sum():.0f} kcal"):
                if not m_data.empty:
                    edited = st.data_editor(m_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True, key=f"d_{meal}_{selected_day}")
                    if not edited.equals(m_data.drop(columns=["Meal"])):
                        edited["Meal"] = meal
                        daily_log = pd.concat([df_f[df_f["Meal"] != meal], edited]).to_dict("records")
                        set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
                        sync_db(db)
                        st.rerun()

        csv_data = df_f.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export Day to CSV", data=csv_data, file_name=f"meals_{selected_day}.csv", mime="text/csv")

        if st.button("🗑️ Reset Selected Day", use_container_width=True):
            set_day_data(user_data, selected_day, [], [], 0.0)
            sync_db(db)
            st.rerun()

    with t_add:
        meal = st.radio("Log to:", MEALS, horizontal=True)
        if st.button("📸 Open Camera Scanner" if not st.session_state.camera_active else "❌ Close Camera"):
            st.session_state.camera_active = not st.session_state.camera_active
            st.rerun()

        code = ""
        if st.session_state.camera_active:
            cam = st.camera_input("Point at barcode", label_visibility="collapsed")
            if cam:
                dec = decode(Image.open(cam))
                if not dec:
                    dec = decode(ImageEnhance.Contrast(Image.open(cam).convert("L")).enhance(3.0))
                if dec:
                    code = dec[0].data.decode("utf-8")
                    st.success("✅ Barcode Detected!")
                    st.session_state.camera_active = False
                else:
                    st.error("❌ Barcode not read. Try moving closer.")

        query = st.text_input("🔍 Search Database:", value=code, placeholder="Type food name or scan barcode")
        if query:
            en = translate_query(query)
            cdb = {**load_fitness_db(), **user_data.get("custom_foods", {})}
            matches = [k for k in cdb.keys() if en in k or query.lower() in k]
            if matches:
                sel = st.selectbox("📑 Best Matches:", matches)
                w = st.number_input("⚖️ Grams eaten:", value=100.0)
                if st.button("➕ Add to Diary", type="primary"):
                    d = cdb[sel]
                    daily_log.append(
                        {
                            "Meal": meal,
                            "Food": sel.title(),
                            "Grams": w,
                            "Calories": round(d["cals"] * w / 100, 1),
                            "Protein": round(d["prot"] * w / 100, 1),
                            "Carbs": round(d["carb"] * w / 100, 1),
                            "Fat": round(d["fat"] * w / 100, 1),
                        }
                    )
                    set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
                    sync_db(db)
                    st.rerun()
            else:
                res = robust_global_search(en)
                if res:
                    opt = {f"{p.get('product_name', 'U')} ({p.get('brands', 'N/A')})": p for p in res[:10]}
                    sel_g = st.selectbox("🌍 Global Search Results:", list(opt.keys()))
                    w = st.number_input("⚖️ Grams eaten:", value=100.0)
                    if st.button("➕ Add to Diary", type="primary"):
                        n = opt[sel_g].get("nutriments", {})
                        daily_log.append(
                            {
                                "Meal": meal,
                                "Food": sel_g,
                                "Grams": w,
                                "Calories": round((n.get("energy-kcal_100g", 0) * w) / 100, 1),
                                "Protein": round((n.get("proteins_100g", 0) * w) / 100, 1),
                                "Carbs": round((n.get("carbohydrates_100g", 0) * w) / 100, 1),
                                "Fat": round((n.get("fat_100g", 0) * w) / 100, 1),
                            }
                        )
                        set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
                        sync_db(db)
                        st.rerun()

    with t_ex:
        st.markdown("### 🏃‍♂️ Scientific Calorie Burner")
        sel_e = st.selectbox("Activity Type:", list(EXERCISE_METS.keys()))
        dur = st.number_input("⏱️ Duration (minutes):", value=45)
        burn = int((EXERCISE_METS[sel_e] * 3.5 * current_weight) / 200 * dur)
        st.info(f"💡 Approx Burned: **{burn} kcal** (Based on your {current_weight}kg weight)")
        if st.button("➕ Log Workout", type="primary"):
            exercise_log.append({"Exercise": sel_e, "Burned": burn})
            set_day_data(user_data, selected_day, daily_log, exercise_log, water_liters)
            sync_db(db)
            st.rerun()
        if exercise_log:
            st.dataframe(pd.DataFrame(exercise_log), use_container_width=True, hide_index=True)

    with t_weight:
        with st.container(border=True):
            w_in = st.number_input("⚖️ Enter Today's Weight (kg)", value=float(current_weight), step=0.1)
            if st.button("💾 Save Weight", use_container_width=True, type="primary"):
                ds = str(date.today())
                user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != ds]
                user_data["weight_log"].append({"Date": ds, "Weight": w_in})
                user_data["weight_log"] = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                sync_db(db)
                st.rerun()

        if len(user_data["weight_log"]) > 0:
            df_w = pd.DataFrame(user_data["weight_log"])
            df_w["Date"] = pd.to_datetime(df_w["Date"])
            sd, sw, g = df_w["Date"].iloc[0], df_w["Weight"].iloc[0], profile.get("goal")
            dr = -0.07 if "Weight Loss" in g else (0.035 if "Muscle" in g else (0.07 if "Bodybuilding" in g else 0))
            df_w["Days"] = (df_w["Date"] - sd).dt.days
            df_w["Ideal"] = sw + (df_w["Days"] * dr)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_w["Date"], y=df_w["Weight"], mode="lines+markers", name="Actual", line=dict(color="#3b82f6", width=4)))
            fig.add_trace(go.Scatter(x=df_w["Date"], y=df_w["Ideal"], mode="lines", name="Target", line=dict(color="#10b981", dash="dash")))
            fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified", legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with t_custom:
        st.markdown("### 👨‍🍳 Recipe & Food Builder")
        cn = st.text_input("📝 Food Name:").lower().strip()
        c1, c2, c3, c4 = st.columns(4)
        cc = c1.number_input("🔥 Cals (100g):")
        cp = c2.number_input("🥩 Pro (100g):")
        cch = c3.number_input("🍞 Carb (100g):")
        cf = c4.number_input("🥑 Fat (100g):")
        if st.button("💾 Save to My Library", type="primary", use_container_width=True):
            if cn:
                user_data.setdefault("custom_foods", {})[cn] = {"cals": cc, "prot": cp, "carb": cch, "fat": cf}
                sync_db(db)
                st.success(f"✅ Saved '{cn}' to your personal database!")


def main():
    init_state()
    db = load_db()

    if not st.session_state.logged_in and "user" in st.query_params:
        saved_user = st.query_params["user"]
        if saved_user in db["users"]:
            st.session_state.logged_in = True
            st.session_state.current_user = saved_user

    if not st.session_state.logged_in:
        auth_screen(db)
    else:
        main_app(db)


if __name__ == "__main__":
    main()
import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator
import plotly.express as px
import plotly.graph_objects as go
import base64
from datetime import date
import json
import os
import io
import time

# --- 0. Database Setup (Persistence) ---
DB_FILE = "myfitness_users_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {"users": {}}
    return {"users": {}}

def sync_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)

db = load_db()

# --- 1. Constants & Motivations ---
EXERCISE_METS = {
    "Weightlifting (Standard)": 5.0, "Weightlifting (Heavy)": 6.0,
    "Running (10 km/h)": 9.8, "Running (12 km/h)": 11.8,
    "Walking (Brisk)": 4.3, "Cycling (Moderate)": 6.8,
    "Swimming (Freestyle)": 8.3, "HIIT / Circuit": 8.0,
    "Yoga / Stretching": 2.5, "Custom (Manual Input)": 0.0
}

OFFLINE_DB = {
    "white bread": {"cals": 265, "prot": 8.0, "carb": 50.0, "fat": 3.0},
    "chicken breast": {"cals": 165, "prot": 31.0, "carb": 0.0, "fat": 3.6},
    "egg": {"cals": 155, "prot": 13.0, "carb": 1.1, "fat": 11.0},
    "cooked rice": {"cals": 130, "prot": 2.7, "carb": 28.0, "fat": 0.3},
    "cottage cheese": {"cals": 95, "prot": 11.0, "carb": 4.0, "fat": 5.0},
    "milk": {"cals": 60, "prot": 3.2, "carb": 4.7, "fat": 3.0},
    "tahini": {"cals": 640, "prot": 24.0, "carb": 12.0, "fat": 54.0},
    "hummus": {"cals": 250, "prot": 8.0, "carb": 14.0, "fat": 18.0},
    "oats": {"cals": 389, "prot": 16.9, "carb": 66.0, "fat": 6.9},
    "bamba": {"cals": 534, "prot": 15.0, "carb": 40.0, "fat": 35.0}
}

MOTIVATIONS = {
    "Weight Loss (Cut)": "קצת רעב עכשיו = תוצאות מחר! תמשיך בגירעון הקלורי, אתה בדרך הנכונה. 💪",
    "Maintenance": "הסוד הוא התמדה! לשמור על מאזן זה לא קל, אבל אתה עושה את זה מעולה. ⚖️",
    "Lean Muscle Gain": "כל אימון וכל ארוחה בונים אותך. אל תשכח את החלבון שלך היום! 🥩",
    "Bodybuilding (Bulk)": "כדי לגדול צריך לאכול! אל תפחד מהפחמימות, הן הדלק שלך לאימון. 🚀"
}

# --- 2. Core Functions ---
@st.cache_data(show_spinner=False)
def translate_query(query):
    try: return GoogleTranslator(source='auto', target='en').translate(query).lower()
    except: return query.lower()

def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("status") == 1: return res.json().get("product")
    except: return None
    return None

def robust_global_search(en_query):
    results, url = [], "https://world.openfoodfacts.org/cgi/search.pl"
    try:
        res = requests.get(url, params={"action": "process", "search_terms": en_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200: results.extend(res.json().get("products", []))
    except: pass
    seen, unique = set(), []
    for p in results:
        name = p.get('product_name')
        if name and name not in seen: seen.add(name); unique.append(p)
    return unique

def calculate_targets(gender, age, weight, height, activity, goal):
    multipliers = {"Sedentary": 1.2, "Lightly active": 1.375, "Moderately active": 1.55, "Very active": 1.725, "Super active": 1.9}
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "Male" else -161)
    tdee = bmr * multipliers[activity]
    if "Weight Loss" in goal: cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif "Maintenance" in goal: cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif "Muscle" in goal: cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else: cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
    prot, carb, fat = int((cals*p_pct)/4), int((cals*c_pct)/4), int((cals*f_pct)/9)
    water = round((weight * 35) / 1000 + (0.75 if "active" in activity.lower() else 0), 1)
    return cals, prot, carb, fat, water

def generate_sms_alert(user_data, rem_c, rem_p, rem_water, goal):
    msg = ""
    if rem_water > 0.5: msg += f"💧 חסר לך עדיין {rem_water:.1f} ליטר מים ליעד! אל תשכח לשתות.\n"
    if rem_p > 20: msg += f"🥩 יש לך עוד {rem_p:.0f} גרם חלבון להשלים היום בשביל השרירים.\n"
    if rem_c > 300: msg += f"🔥 נשארו לך {rem_c:.0f} קלוריות! זמן לארוחה טובה.\n"
    if not msg: msg = "🏆 עמדת בכל היעדים שלך להיום! עבודה מדהימה."
    msg += f"\n💡 {MOTIVATIONS.get(goal, '')}"
    return msg

def send_real_sms_mock(phone_number, text_message):
    """
    זו הפונקציה שבעתיד תתחבר ל-API אמיתי כמו Twilio.
    כרגע היא רק מדמה שליחה.
    """
    # example real code: requests.post("https://api.twilio.com/...", data={"to": phone_number, "body": text_message})
    print(f"MOCK SMS SENT TO {phone_number}: {text_message}")
    return True

# --- 3. Soft UI Config ---
st.set_page_config(page_title="MyFitness Pro", page_icon="🍏", layout="centered")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Heebo', sans-serif; }
    .app-title { text-align: center; color: #1e293b; font-weight: 800; font-size: 2.2rem; margin-bottom: 5px; }
    .app-subtitle { text-align: center; color: #64748b; font-size: 1rem; margin-top: 0px; margin-bottom: 25px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: none; justify-content: center; }
    .stTabs [data-baseweb="tab"] { border-radius: 12px; padding: 10px 16px; color: #64748b; font-weight: 500; background-color: #f1f5f9; border: none; }
    .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; font-weight: 700; box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3); }
    div[data-testid="stMetric"] { background-color: #ffffff; padding: 15px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #f1f5f9; text-align: center; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #0f172a; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem; font-weight: 600; color: #64748b; margin-bottom: 5px; }
    [data-testid="stExpander"] { border-radius: 16px !important; border: 1px solid #e2e8f0 !important; }
    header {visibility: hidden;} footer {visibility: hidden;} [data-testid="stToolbar"] {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 4. Auth State & Auto-Login ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = "Login"
if 'camera_active' not in st.session_state: st.session_state.camera_active = False

if not st.session_state.logged_in and "user" in st.query_params:
    saved_user = st.query_params["user"]
    if saved_user in db["users"]:
        st.session_state.logged_in = True
        st.session_state.current_user = saved_user

# ==========================================
# AUTHENTICATION SCREEN
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 class='app-title'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Your Personal Nutrition & Training App</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### 👋 Welcome Back")
                with st.form("login_form"):
                    le = st.text_input("📧 Email").lower().strip()
                    lp = st.text_input("🔒 Password", type="password")
                    remember = st.checkbox("💾 Remember Me", value=True)
                    submit_btn = st.form_submit_button("Log In", type="primary", use_container_width=True)
                    if submit_btn:
                        if le in db["users"] and db["users"][le]["password"] == lp:
                            st.session_state.logged_in = True
                            st.session_state.current_user = le
                            if remember: st.query_params["user"] = le 
                            st.rerun()
                        else: st.error("Wrong email or password.")
                st.write("")
                if st.button("New here? Create Account", use_container_width=True): 
                    st.session_state.auth_mode = "Register"; st.rerun()
                
            elif st.session_state.auth_mode == "Register":
                st.markdown("### ✨ Create Account")
                with st.form("register_form"):
                    re = st.text_input("📧 Email").lower().strip()
                    rp = st.text_input("🔒 Password", type="password")
                    reg_btn = st.form_submit_button("Get Started", type="primary", use_container_width=True)
                    if reg_btn:
                        if re in db["users"]: st.error("Account exists!")
                        elif re and len(rp) >= 4:
                            st.session_state.temp_reg = {"e": re, "p": rp}; st.session_state.auth_mode = "Verify"; st.rerun()
                        else: st.error("Enter valid email and password (min 4 chars)")
                if st.button("⬅️ Back to Login"): st.session_state.auth_mode = "Login"; st.rerun()
                
            elif st.session_state.auth_mode == "Verify":
                st.info("💡 Hint: Enter '1234' to verify")
                with st.form("verify_form"):
                    vc = st.text_input("Enter 4-digit code")
                    v_btn = st.form_submit_button("Verify Account", type="primary", use_container_width=True)
                    if v_btn:
                        if vc == "1234":
                            email = st.session_state.temp_reg["e"]
                            db["users"][email] = {
                                "password": st.session_state.temp_reg["p"], "username": email.split('@')[0], "profile_pic": "", "phone": "", "sms_alerts": False,
                                "onboarding_done": False, "profile": {}, "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water_liters": 0.0
                            }
                            sync_db(); st.session_state.logged_in = True; st.session_state.current_user = email; st.query_params["user"] = email; st.rerun()

# ==========================================
# MAIN APP
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    
    if "username" not in user_data: user_data["username"] = st.session_state.current_user.split('@')[0]
    if "profile_pic" not in user_data: user_data["profile_pic"] = ""
    if "phone" not in user_data: user_data["phone"] = ""
    if "sms_alerts" not in user_data: user_data["sms_alerts"] = False
    
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'>🎯 Let's build your plan</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            col1, col2 = st.columns(2)
            gen = col1.selectbox("🚻 Gender", ["Male", "Female"])
            age = col2.number_input("🎂 Age", min_value=10, value=21)
            weight = col1.number_input("⚖️ Weight (kg)", min_value=30.0, value=75.0)
            height = col2.number_input("📏 Height (cm)", min_value=100.0, value=175.0)
            act = st.selectbox("🏃‍♂️ Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"])
            goal = st.selectbox("🎯 Your Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
            if st.button("🚀 Calculate My Plan", type="primary", use_container_width=True):
                cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
                user_data.update({"profile": {"gender": gen, "age": age, "height": height, "activity": act, "goal": goal, "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water}}, "weight_log": [{"Date": str(date.today()), "Weight": weight}], "onboarding_done": True})
                sync_db(); st.rerun()

    else:
        profile = user_data["profile"]
        targets = profile["targets"]
        w_log = user_data.get("weight_log", [])
        try: current_weight = sorted(w_log, key=lambda x: x["Date"])[-1]["Weight"] if w_log else 75.0
        except: current_weight = 75.0
        recommended_water = calculate_targets(profile["gender"], profile["age"], current_weight, profile["height"], profile["activity"], profile["goal"])[4]

        # --- SIDEBAR MENU ---
        with st.sidebar:
            c1, c2 = st.columns([1, 2.5])
            pic_b64 = user_data.get("profile_pic", "")
            with c1:
                if pic_b64: st.markdown(f'<img src="data:image/jpeg;base64,{pic_b64}" style="width:65px; height:65px; border-radius:50%; object-fit:cover; border:2px solid #3b82f6;">', unsafe_allow_html=True)
                else: st.markdown(f"<div style='font-size: 55px;'>👤</div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<h3 style='margin-bottom:0px; padding-top:10px;'>{user_data.get('username')}</h3>", unsafe_allow_html=True)
                if st.button("🚪 Logout", use_container_width=True): 
                    st.session_state.logged_in = False; st.query_params.clear(); st.rerun()
            st.divider()

            # --- ACCOUNT & PHONE SETTINGS ---
            with st.expander("📝 Account & Alerts"):
                old_phone = user_data.get("phone", "")
                old_sms = user_data.get("sms_alerts", False)
                
                new_username = st.text_input("Username", value=user_data.get("username"))
                new_phone = st.text_input("📱 Phone (For Alerts)", value=old_phone, placeholder="e.g. 0501234567")
                sms_toggle = st.checkbox("🔔 Enable SMS Reminders", value=old_sms)
                new_pic = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png"])
                
                if st.button("💾 Save Settings", use_container_width=True):
                    taken = any(u.get("username") == new_username for k, u in db["users"].items() if k != st.session_state.current_user)
                    if taken: st.error("Username is taken!")
                    else:
                        user_data["username"] = new_username
                        user_data["phone"] = new_phone
                        user_data["sms_alerts"] = sms_toggle
                        if new_pic:
                            img = Image.open(new_pic).convert("RGB")
                            img.thumbnail((150, 150))
                            buffered = io.BytesIO()
                            img.save(buffered, format="JPEG")
                            user_data["profile_pic"] = base64.b64encode(buffered.getvalue()).decode()
                        sync_db()
                        
                        # --- SMS WELCOME LOGIC ---
                        # If user just enabled SMS or changed their phone number while SMS is enabled
                        if sms_toggle and (new_phone != old_phone or not old_sms) and new_phone != "":
                            welcome_msg = "שלום! 🍏 שמחים שהצטרפת לשירות ה-SMS וההתראות של MyFitness Pro. אנחנו כאן כדי לעזור לך להגיע ליעדים שלך! 💪"
                            send_real_sms_mock(new_phone, welcome_msg)
                            st.balloons()
                            st.toast(f"📲 נשלח SMS ברוך הבא למספר {new_phone}!")
                            time.sleep(2) # Give the user time to see the toast before rerun
                        
                        st.success("Profile Saved!")
                        st.rerun()

            with st.expander("⚖️ Edit Body Profile"):
                new_gen = st.selectbox("Gender", ["Male", "Female"], index=["Male", "Female"].index(profile.get("gender", "Male")))
                new_age = st.number_input("Age", value=int(profile.get("age", 21)), min_value=10)
                new_height = st.number_input("Height (cm)", value=int(profile.get("height", 175)), min_value=100)
                new_act = st.selectbox("Activity", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"], index=["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"].index(profile["activity"]))
                new_goal = st.selectbox("Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"], index=["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"].index(profile["goal"]))
                if st.button("🔄 Recalculate Targets", use_container_width=True):
                    c, p, cb, f, w = calculate_targets(new_gen, new_age, current_weight, new_height, new_act, new_goal)
                    user_data["profile"].update({"gender": new_gen, "age": new_age, "height": new_height, "activity": new_act, "goal": new_goal, "targets": {"cals": c, "prot": p, "carb": cb, "fat": f, "water": w}})
                    sync_db(); st.success("Updated!"); st.rerun()
                
            with st.expander("🎯 Edit Targets Manually"):
                t_cals = st.number_input("🔥 Calories", value=targets["cals"], step=50)
                t_prot = st.number_input("🥩 Protein (g)", value=targets["prot"], step=5)
                t_carb = st.number_input("🍞 Carbs (g)", value=targets["carb"], step=5)
                t_fat = st.number_input("🥑 Fat (g)", value=targets["fat"], step=5)
                if st.button("💾 Save Manual Targets", use_container_width=True):
                    user_data["profile"]["targets"].update({"cals": t_cals, "prot": t_prot, "carb": t_carb, "fat": t_fat}); sync_db(); st.rerun()

            st.divider()
            st.markdown("### 💧 Hydration Station")
            user_water_goal = st.number_input("🎯 Goal (L)", value=float(targets.get("water", recommended_water)), step=0.25)
            if user_water_goal != targets.get("water"): user_data["profile"]["targets"]["water"] = user_water_goal; sync_db()
            
            w_c1, w_c2, w_c3 = st.columns([1,1,1])
            if w_c1.button("➖", use_container_width=True): user_data["water_liters"] = max(0.0, user_data.get("water_liters", 0.0) - 0.25); sync_db()
            w_c2.markdown(f"<h3 style='text-align:center; color:#3b82f6;'>{user_data.get('water_liters', 0.0):.2f}L</h3>", unsafe_allow_html=True)
            if w_c3.button("➕", use_container_width=True): user_data["water_liters"] = user_data.get("water_liters", 0.0) + 0.25; sync_db()
            st.progress(min(user_data.get("water_liters", 0.0) / user_water_goal, 1.0) if user_water_goal > 0 else 0)

        # --- MAIN TABS ---
        st.markdown("<h1 class='app-title'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
        t_dash, t_add, t_ex, t_weight, t_custom = st.tabs(["📊 Summary", "🍏 Add Food", "👟 Exercise", "📈 Weight", "👨‍🍳 Recipes"])

        # TAB 1: DASHBOARD
        with t_dash:
            df_f = pd.DataFrame(user_data.get("daily_log", []))
            if df_f.empty: df_f = pd.DataFrame(columns=["Meal", "Food", "Grams", "Calories", "Protein", "Carbs", "Fat"])
            df_e = pd.DataFrame(user_data.get("exercise_log", []))
            if df_e.empty: df_e = pd.DataFrame(columns=["Exercise", "Burned"])

            t_food, t_burn = df_f['Calories'].sum(), df_e['Burned'].sum()
            rem_c = targets["cals"] - (t_food - t_burn)
            
            # --- NOTIFICATIONS HUB ---
            if user_data.get("sms_alerts") and user_data.get("phone"):
                rem_p = max(0, targets["prot"] - df_f['Protein'].sum())
                rem_w = max(0, targets["water"] - user_data.get("water_liters", 0.0))
                sms_text = generate_sms_alert(user_data, rem_c, rem_p, rem_w, profile.get("goal"))
                
                st.info(f"📱 **SMS Alerts Active ({user_data['phone']})**")
                with st.expander("📬 View Pending Alerts & Motivation"):
                    st.write(sms_text)
                    if st.button("🔔 Send Test SMS Now", type="secondary"):
                        send_real_sms_mock(user_data['phone'], sms_text)
                        st.toast("✅ SMS Sent successfully! (Simulation)")
            
            # --- METRICS ---
            st.markdown("### 🔋 Energy Balance")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🎯 Goal", targets["cals"])
            m2.metric("🍔 Food", f"{t_food:.0f}")
            m3.metric("🔥 Burned", f"{t_burn:.0f}")
            m4.metric("📉 Left", f"{rem_c:.0f}" if rem_c >= 0 else f"⚠️ {abs(rem_c):.0f} Over")
            st.progress(min(max(0, (t_food - t_burn) / targets["cals"]), 1.0) if targets["cals"] > 0 else 0)
            
            st.write("")
            col_ma, col_pi = st.columns([1.2, 1])
            with col_ma:
                st.markdown("### 🥩 Macros")
                for m, cur, goal, color, icon in [("Protein", df_f['Protein'].sum(), targets["prot"], "#ef4444", "🥩"), ("Carbs", df_f['Carbs'].sum(), targets["carb"], "#3b82f6", "🍞"), ("Fat", df_f['Fat'].sum(), targets["fat"], "#10b981", "🥑")]:
                    diff = goal - cur
                    status = f"{diff:.0f}g left" if diff >= 0 else f"⚠️ Over {abs(diff):.0f}g"
                    st.markdown(f"**{icon} {m}:** {cur:.0f}g / {goal}g | <span style='color:{color if diff >= 0 else '#dc2626'}; font-weight:600;'>{status}</span>", unsafe_allow_html=True)
                    st.progress(min(cur / goal, 1.0) if goal > 0 else 0)
            with col_pi:
                fig = px.pie(pd.DataFrame({"M": ["Pro", "Carb", "Fat"], "G": [df_f['Protein'].sum(), df_f['Carbs'].sum(), df_f['Fat'].sum()]}), values='G', names='M', hole=0.5, color_discrete_sequence=['#ef4444', '#3b82f6', '#10b981'])
                fig.update_layout(height=180, showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            st.markdown("### 🍽️ Meals Diary")
            for meal, icon in [("Breakfast", "🍳"), ("Lunch", "🥗"), ("Dinner", "🍱"), ("Snacks", "🍎")]:
                m_data = df_f[df_f["Meal"] == meal]
                with st.expander(f"{icon} {meal} | {m_data['Calories'].sum():.0f} kcal"):
                    if not m_data.empty:
                        edited = st.data_editor(m_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True, key=f"d_{meal}")
                        if not edited.equals(m_data.drop(columns=["Meal"])):
                            edited["Meal"] = meal
                            user_data["daily_log"] = pd.concat([df_f[df_f["Meal"] != meal], edited]).to_dict('records')
                            sync_db(); st.rerun()

            st.write("")
            if st.button("🗑️ Reset Entire Day", use_container_width=True): 
                user_data.update({"daily_log": [], "exercise_log": [], "water_liters": 0.0}); sync_db(); st.rerun()

        # TAB 2: ADD FOOD
        with t_add:
            meal = st.radio("Log to:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
            
            if st.button("📸 Open Camera Scanner" if not st.session_state.camera_active else "❌ Close Camera"):
                st.session_state.camera_active = not st.session_state.camera_active
                st.rerun()
            
            code = ""
            if st.session_state.camera_active:
                cam = st.camera_input("Point at barcode", label_visibility="collapsed")
                if cam:
                    dec = decode(Image.open(cam))
                    if not dec: dec = decode(ImageEnhance.Contrast(Image.open(cam).convert('L')).enhance(3.0))
                    if dec: 
                        code = dec[0].data.decode("utf-8"); st.success("✅ Barcode Detected!"); st.session_state.camera_active = False 
                    else: st.error("❌ Barcode not read. Try moving closer.")

            query = st.text_input("🔍 Search Database:", value=code, placeholder="Type food name or scan barcode")
            if query:
                en = translate_query(query)
                CDB = {**OFFLINE_DB, **user_data.get("custom_foods", {})}
                matches = [k for k in CDB.keys() if en in k or query.lower() in k]
                if matches:
                    sel = st.selectbox("📑 Best Matches:", matches)
                    w = st.number_input("⚖️ Grams eaten:", value=100.0)
                    if st.button("➕ Add to Diary", type="primary"):
                        d = CDB[sel]
                        user_data["daily_log"].append({"Meal": meal, "Food": sel.title(), "Grams": w, "Calories": round(d["cals"]*w/100,1), "Protein": round(d["prot"]*w/100,1), "Carbs": round(d["carb"]*w/100,1), "Fat": round(d["fat"]*w/100,1)})
                        sync_db(); st.rerun()
                else:
                    res = robust_global_search(en)
                    if res:
                        opt = {f"{p.get('product_name','U')} ({p.get('brands','N/A')})": p for p in res[:10]}
                        sel_g = st.selectbox("🌍 Global Search Results:", list(opt.keys()))
                        w = st.number_input("⚖️ Grams eaten:", value=100.0)
                        if st.button("➕ Add to Diary", type="primary"):
                            n = opt[sel_g].get('nutriments', {})
                            user_data["daily_log"].append({"Meal": meal, "Food": sel_g, "Grams": w, "Calories": round((n.get("energy-kcal_100g",0)*w)/100, 1), "Protein": round((n.get("proteins_100g",0)*w)/100, 1), "Carbs": round((n.get("carbohydrates_100g",0)*w)/100, 1), "Fat": round((n.get("fat_100g",0)*w)/100, 1)})
                            sync_db(); st.rerun()

        # TAB 3: WORKOUTS
        with t_ex:
            st.markdown("### 🏃‍♂️ Scientific Calorie Burner")
            sel_e = st.selectbox("Activity Type:", list(EXERCISE_METS.keys()))
            dur = st.number_input("⏱️ Duration (minutes):", value=45)
            burn = int((EXERCISE_METS[sel_e] * 3.5 * current_weight) / 200 * dur)
            st.info(f"💡 Approx Burned: **{burn} kcal** (Based on your {current_weight}kg weight)")
            if st.button("➕ Log Workout", type="primary"):
                user_data["exercise_log"].append({"Exercise": sel_e, "Burned": burn}); sync_db(); st.rerun()
            if user_data["exercise_log"]: st.dataframe(pd.DataFrame(user_data["exercise_log"]), use_container_width=True, hide_index=True)

        # TAB 4: WEIGHT TRACKER
        with t_weight:
            with st.container(border=True):
                w_in = st.number_input("⚖️ Enter Today's Weight (kg)", value=float(current_weight), step=0.1)
                if st.button("💾 Save Weight", use_container_width=True, type="primary"):
                    ds = str(date.today())
                    user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != ds]
                    user_data["weight_log"].append({"Date": ds, "Weight": w_in})
                    user_data["weight_log"] = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                    sync_db(); st.rerun()
            
            if len(user_data["weight_log"]) > 0:
                df_w = pd.DataFrame(user_data["weight_log"])
                df_w['Date'] = pd.to_datetime(df_w['Date'])
                sd, sw, g = df_w['Date'].iloc[0], df_w['Weight'].iloc[0], profile.get("goal")
                dr = -0.07 if "Weight Loss" in g else (0.035 if "Muscle" in g else (0.07 if "Bodybuilding" in g else 0))
                df_w['Days'] = (df_w['Date'] - sd).dt.days
                df_w['Ideal'] = sw + (df_w['Days'] * dr)
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Weight'], mode='lines+markers', name='Actual', line=dict(color='#3b82f6', width=4)))
                fig.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Ideal'], mode='lines', name='Target', line=dict(color='#10b981', dash='dash')))
                fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified", legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown("#### 📋 Weight History (Read Only)")
                disp_df = df_w[['Date', 'Weight']].copy()
                disp_df['Date'] = disp_df['Date'].dt.strftime('%Y-%m-%d')
                st.dataframe(disp_df.sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

        # TAB 5: CUSTOM FOODS
        with t_custom:
            st.markdown("### 👨‍🍳 Recipe & Food Builder")
            cn = st.text_input("📝 Food Name:").lower()
            c1, c2, c3, c4 = st.columns(4)
            cc = c1.number_input("🔥 Cals (100g):")
            cp = c2.number_input("🥩 Pro (100g):")
            cch = c3.number_input("🍞 Carb (100g):")
            cf = c4.number_input("🥑 Fat (100g):")
            if st.button("💾 Save to My Library", type="primary", use_container_width=True):
                if cn: 
                    if "custom_foods" not in user_data: user_data["custom_foods"] = {}
                    user_data["custom_foods"][cn] = {"cals":cc, "prot":cp, "carb":cch, "fat":cf}
                    sync_db(); st.success(f"✅ Saved '{cn}' to your personal database!")