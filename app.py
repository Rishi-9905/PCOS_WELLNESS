from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import random
import sys
import os
from datetime import datetime


# Get the current directory of this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Add script path to sys.path so we can import it
sys.path.append(BASE_DIR)

from PCOS_FINAL_MODEL import clf, feature_columns, df_map, preprocess_input  # import your trained model & mapping

app = Flask(__name__)
app.secret_key = "pcos_secret_key" # Needed for sessions

# Path for logging
LOG_FILE = os.path.join(BASE_DIR, "User_Analysis_Logs.xlsx")
USER_FILE = os.path.join(BASE_DIR, "users.xlsx")
POSTS_FILE = os.path.join(BASE_DIR, "community_posts.xlsx")
COMMENTS_FILE = os.path.join(BASE_DIR, "comments.xlsx")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "posts")

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------- Helper Functions ----------
substitutions = {
    "apple": ["pear", "orange", "peach", "plum"],
    "banana": ["mango", "papaya", "peach"],
    "nuts": ["roasted chickpeas", "pumpkin seeds", "sunflower seeds"],
    "milk": ["soy milk", "almond milk", "oat milk"],
    "cheese": ["tofu", "nutritional yeast"],
    "egg": ["tofu scramble", "chickpea flour omelette"],
    "chicken": ["tofu", "tempeh", "seitan"],
    "fish": ["tofu", "tempeh", "edamame"],
    "soy": ["lentils", "chickpeas", "green peas"]
}

def is_allowed(item: str, diet_type: str, allergies: list) -> bool:
    lower = item.lower()
    if diet_type == "vegan" and any(x in lower for x in ["egg", "milk", "cheese", "butter", "ghee", "honey"]):
        return False
    if diet_type == "vegetarian" and any(x in lower for x in ["chicken", "fish", "meat", "prawn"]):
        return False
    if any(a in lower for a in allergies):
        return False
    return True

# Mock Email Reminder Function
def send_reminder_email(username, email):
    with open("email_logs.txt", "a") as f:
        f.write(f"To: {email}\nSubject: Wellness Reminder for {username}\n")
        f.write("Hi! We missed you. Consistency is key to managing PCOS. Come back and check in with your PCOS Assistant today!\n")
        f.write("-" * 30 + "\n")
    print(f"Mock email sent to {email}")

def get_users():
    if not os.path.exists(USER_FILE):
        return pd.DataFrame(columns=['username', 'email', 'password', 'last_login'])
    df = pd.read_excel(USER_FILE)
    if 'email' not in df.columns:
        df['email'] = ""
    if 'last_login' not in df.columns:
        df['last_login'] = ""
    return df

def save_user(username, password):
    df_users = get_users()
    new_user = pd.DataFrame([{'username': username, 'password': password}])
    df_users = pd.concat([df_users, new_user], ignore_index=True)
    df_users.to_excel(USER_FILE, index=False)

def log_user_data(username, answers, results):
    """Logs user inputs and outputs to an Excel file."""
    # Create the log entry with Username first
    log_entry = {'Username': username, 'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    log_entry.update(answers)
    log_entry['Recommended_Categories'] = ", ".join(results.keys())
    
    df_log = pd.DataFrame([log_entry])

    
    try:
        if not os.path.isfile(LOG_FILE):
            df_log.to_excel(LOG_FILE, index=False)
        else:
            existing_df = pd.read_excel(LOG_FILE)
            updated_df = pd.concat([existing_df, df_log], ignore_index=True)
            updated_df.to_excel(LOG_FILE, index=False)
    except Exception as e:
        print(f"Logging error: {e}")


# ---------- Routes ----------

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        df_users = get_users()
        user_match = df_users[(df_users['username'] == username) & (df_users['password'] == password)]
        
        if not user_match.empty:
            session['user'] = username
            
            # Check for reminder (24h gap)
            last_login_raw = user_match.iloc[0].get('last_login')
            user_email = user_match.iloc[0].get('email')
            
            if last_login_raw and not pd.isna(last_login_raw) and last_login_raw != "":
                try:
                    last_login_dt = datetime.strptime(str(last_login_raw), "%Y-%m-%d %H:%M:%S")
                    if (datetime.now() - last_login_dt).total_seconds() > 86400:
                        send_reminder_email(username, user_email)
                except Exception as e:
                    print(f"Reminder check error: {e}")
            
            # Update last login to now
            df_users.loc[df_users['username'] == username, 'last_login'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df_users.to_excel(USER_FILE, index=False)
            
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid username or password")
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if os.path.exists(USER_FILE):
            df = pd.read_excel(USER_FILE)
            # Ensure 'email' column exists for older databases
            if 'email' not in df.columns:
                df['email'] = ""
        else:
            df = pd.DataFrame(columns=['username', 'email', 'password'])
            
        if username in df['username'].values:
            return render_template('register.html', error="Username already exists!")
            
        new_user = pd.DataFrame([[username, email, password]], columns=['username', 'email', 'password'])
        df = pd.concat([df, new_user], ignore_index=True)
        df.to_excel(USER_FILE, index=False)
        
        return render_template('login.html', success="Registration successful! Please login.")
        
    return render_template('register.html')

# ---------- Community Logic ----------
def get_posts():
    if not os.path.exists(POSTS_FILE):
        return pd.DataFrame(columns=['id', 'username', 'content', 'image_path', 'timestamp', 'likes'])
    df = pd.read_excel(POSTS_FILE)
    if 'likes' not in df.columns:
        df['likes'] = 0
    return df.sort_values(by='timestamp', ascending=False)

def get_comments(post_id=None):
    if not os.path.exists(COMMENTS_FILE):
        return pd.DataFrame(columns=['post_id', 'username', 'comment', 'timestamp'])
    try:
        df = pd.read_excel(COMMENTS_FILE)
        # Ensure post_id is consistently string
        df['post_id'] = df['post_id'].astype(str)
        if post_id:
            return df[df['post_id'] == str(post_id)].sort_values(by='timestamp', ascending=True)
        return df
    except:
        return pd.DataFrame(columns=['post_id', 'username', 'comment', 'timestamp'])

@app.route('/community')
def community():
    if 'user' not in session:
        return redirect(url_for('login'))
    posts_df = get_posts()
    # Ensure post IDs are strings for matching
    posts_df['id'] = posts_df['id'].astype(str)
    posts = posts_df.to_dict('records')
    
    # Merge comments into posts
    for post in posts:
        post_comments = get_comments(post['id'])
        post['comments'] = post_comments.to_dict('records')
        post['comment_count'] = len(post['comments'])
        
    return render_template('community.html', username=session['user'], posts=posts)

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    username = session['user']
    content = request.form.get('content')
    file = request.files.get('image')
    
    image_path = ""
    if file and file.filename != '':
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = f"uploads/posts/{filename}"
        
    posts_df = get_posts()
    new_post = pd.DataFrame([{
        'id': str(datetime.now().timestamp()),
        'username': username,
        'content': content,
        'image_path': image_path,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'likes': 0
    }])
    
    posts_df = pd.concat([posts_df, new_post], ignore_index=True)
    posts_df.to_excel(POSTS_FILE, index=False)
    
    return redirect(url_for('community'))

@app.route('/delete_post/<post_id>')
def delete_post(post_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    posts_df = get_posts()
    # Robust string comparison
    posts_df['id'] = posts_df['id'].astype(str)
    post = posts_df[posts_df['id'] == str(post_id)]
    
    if not post.empty and post.iloc[0]['username'] == session['user']:
        # Delete image file if exists and is not NaN
        img_path = post.iloc[0]['image_path']
        if isinstance(img_path, str) and img_path.strip():
            full_path = os.path.join(BASE_DIR, 'static', img_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except:
                    pass
        
        posts_df = posts_df[posts_df['id'] != str(post_id)]
        posts_df.to_excel(POSTS_FILE, index=False)
        
        # Also delete associated comments
        if os.path.exists(COMMENTS_FILE):
            comments_df = pd.read_excel(COMMENTS_FILE)
            comments_df['post_id'] = comments_df['post_id'].astype(str)
            comments_df = comments_df[comments_df['post_id'] != str(post_id)]
            comments_df.to_excel(COMMENTS_FILE, index=False)
            
    return redirect(url_for('community'))

@app.route('/like_post/<post_id>')
def like_post(post_id):
    if 'user' not in session:
        return redirect(url_for('login'))
        
    posts_df = get_posts()
    posts_df['id'] = posts_df['id'].astype(str)
    idx = posts_df[posts_df['id'] == str(post_id)].index
    if not idx.empty:
        posts_df.loc[idx, 'likes'] = posts_df.loc[idx, 'likes'].fillna(0) + 1
        posts_df.to_excel(POSTS_FILE, index=False)
        
    return redirect(url_for('community'))

@app.route('/add_comment/<post_id>', methods=['POST'])
def add_comment(post_id):
    if 'user' not in session:
        return redirect(url_for('login'))
        
    comment_text = request.form.get('comment')
    if not comment_text:
        return redirect(url_for('community'))
        
    comments_df = get_comments()
    new_comment = pd.DataFrame([{
        'post_id': str(post_id),
        'username': session['user'],
        'comment': comment_text,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    
    comments_df = pd.concat([comments_df, new_comment], ignore_index=True)
    comments_df.to_excel(COMMENTS_FILE, index=False)
    
    return redirect(url_for('community'))

@app.route('/profile')

def profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    username = session['user']
    history = []
    if os.path.exists(LOG_FILE):
        df_logs = pd.read_excel(LOG_FILE)
        user_logs = df_logs[df_logs['Username'] == username]
        history = user_logs.sort_values(by='Timestamp', ascending=False).to_dict('records')
    
    return render_template('profile.html', username=username, history=history)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/predict', methods=['POST'])
def predict():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Get user inputs from the form
    answers = {key: request.form[key] for key in request.form}

    # Split allergies and dislikes
    allergies = [a.strip().lower() for a in answers.get("Allergies", "").split(",") if a.strip()]
    disliked_items = [d.strip().lower() for d in answers.get("Disliked_Items", "").split(",") if d.strip()]
    diet_type = answers.get("Diet_Type", "").lower()

    # Convert numeric fields
    try:
        answers["Age"] = int(answers.get("Age", 0))
        answers["Weight"] = float(answers.get("Weight", 0))
        answers["Height"] = float(answers.get("Height", 0))
        answers["Sleep_Hours"] = float(answers.get("Sleep_Hours", 0))
        answers["Cycle_Length"] = float(answers.get("Cycle_Length", 0) or 0)
        answers["Duration_Menstruation"] = float(answers.get("Duration_Menstruation", 0) or 0)
        answers["Pregnancies"] = int(answers.get("Pregnancies", 0))
        answers["Insulin_Level"] = float(answers.get("Insulin_Level", 0) or 0)
    except ValueError as e:
        print(f"Error converting inputs: {e}")
        # Proceed with defaults or handle error - for now letting it proceed with what we have


    # Prepare input for model
    processed_answers = preprocess_input(answers.copy())
    new_df = pd.DataFrame([processed_answers])

    new_df_encoded = pd.get_dummies(new_df, drop_first=True)
    new_df_encoded = new_df_encoded.reindex(columns=feature_columns, fill_value=0)

    # Predict
    new_pred = clf.predict(new_df_encoded)[0]
    diet_cols = df_map['diet_label'].tolist()

    # Map predictions to foods
    recommended_foods = {}
    for label, flag in zip(diet_cols, new_pred):
        if flag != 1:
            continue
        safe_foods = []
        for food in df_map[df_map['diet_label'] == label].iloc[0, 1:].dropna():
            f_low = str(food).strip().lower()
            if not is_allowed(f_low, diet_type, allergies):
                continue
            if f_low in disliked_items:
                if f_low in substitutions:
                    subs_safe = [s for s in substitutions[f_low] if is_allowed(s, diet_type, allergies)]
                    if subs_safe:
                        safe_foods.append(f"{food} (disliked) → Try: {', '.join(subs_safe)}")
                    else:
                        safe_foods.append(f"{food} (disliked) → No safe substitute")
                else:
                    safe_foods.append(f"{food} (disliked) → No substitute listed")
            else:
                safe_foods.append(food)
            recommended_foods[label] = safe_foods
    
    # Log the successful prediction
    log_user_data(session.get('user'), answers, recommended_foods)

    return render_template('result.html', recommended_foods=recommended_foods)

@app.route('/chat', methods=['POST'])
def chat():

    user_msg = request.json.get("message", "").lower()
    
    # Personality-driven response dictionary with lists for variety
    responses = {
        "what is pcos": [
            "Polycystic Ovary Syndrome (PCOS) is a hormonal disorder in women where the ovaries produce excess male hormones, which can cause irregular periods, cysts in the ovaries, weight gain, acne, and difficulty in ovulation."
        ],
        "what causes pcos": [
            "The exact cause of Polycystic Ovary Syndrome (PCOS) is unknown, but it is commonly linked to hormonal imbalance, insulin resistance, genetic factors, and excess production of male hormones (androgens)."
        ],
        "cause pcos": [
            "The exact cause of Polycystic Ovary Syndrome (PCOS) is unknown, but it is commonly linked to hormonal imbalance, insulin resistance, genetic factors, and excess production of male hormones (androgens)."
        ],
        "stress or mental health cause": [
            "Stress does not directly cause PCOS, but long-term stress can worsen symptoms by affecting hormones and insulin levels."
        ],
        "lifestyle imbalance": [
            "Lifestyle imbalance does not directly cause Polycystic Ovary Syndrome (PCOS), but unhealthy habits such as poor diet, lack of exercise, irregular sleep, and high stress can increase the risk and worsen its symptoms."
        ],
        "healthy lifestyle reduce": [
            "Yes, maintaining a healthy lifestyle can help manage and reduce the symptoms of Polycystic Ovary Syndrome (PCOS). Regular exercise, a balanced diet, proper sleep, and stress management can improve hormone balance and insulin levels."
        ],
        "is pcos common": [
            "Yes, Polycystic Ovary Syndrome (PCOS) is very common. It affects about 10-13% of women of reproductive age worldwide, which is roughly 1 in 10 women."
        ],
        "what age does pcos usually start": [
            "Polycystic Ovary Syndrome (PCOS) usually starts during adolescence or early reproductive years, often between ages 15 and 25, sometimes soon after the first menstrual periods."
        ],
        "age does pcos": [
            "Polycystic Ovary Syndrome (PCOS) usually starts during adolescence or early reproductive years, often between ages 15 and 25, sometimes soon after the first menstrual periods."
        ],
        "is pcos a serious condition": [
            "Polycystic Ovary Syndrome (PCOS) is not usually life-threatening, but it can lead to health issues like irregular periods, infertility, weight gain, and increased risk of conditions such as Type 2 Diabetes if not managed properly."
        ],
        "serious condition": [
            "Polycystic Ovary Syndrome (PCOS) is not usually life-threatening, but it can lead to health issues like irregular periods, infertility, weight gain, and increased risk of conditions such as Type 2 Diabetes if not managed properly."
        ],
        "common symptoms of pcos": [
            "Common symptoms of Polycystic Ovary Syndrome (PCOS) include irregular or missed periods, weight gain, acne, excessive facial or body hair, hair thinning on the scalp, and difficulty getting pregnant."
        ],
        "symptoms of pcos": [
            "Common symptoms of Polycystic Ovary Syndrome (PCOS) include irregular or missed periods, weight gain, acne, excessive facial or body hair, hair thinning on the scalp, and difficulty getting pregnant."
        ],
        "irregular periods": [
            "Yes, Polycystic Ovary Syndrome (PCOS) commonly causes irregular, infrequent, or missed menstrual periods due to hormonal imbalance."
        ],
        "weight gain": [
            "Yes, Polycystic Ovary Syndrome (PCOS) can cause weight gain, especially around the abdomen, often linked to insulin resistance."
        ],
        "weight loss": [
            "Yes, even losing 5-10% of body weight can help improve symptoms of Polycystic Ovary Syndrome."
        ],
        "acne or hair growth": [
            "Yes, Polycystic Ovary Syndrome (PCOS) can cause acne and excessive facial or body hair due to increased male hormones (androgens)."
        ],
        "affect fertility": [
            "Yes, Polycystic Ovary Syndrome (PCOS) can affect fertility because irregular ovulation may make it harder to get pregnant."
        ],
        "diagnosed": [
            "Polycystic Ovary Syndrome (PCOS) is diagnosed through medical history, symptom evaluation, physical examination, blood tests, and ultrasound."
        ],
        "tests are needed": [
            "Common tests for Polycystic Ovary Syndrome (PCOS) include hormone blood tests, pelvic ultrasound, and tests for insulin or glucose levels."
        ],
        "confirm pcos": [
            "Common tests for Polycystic Ovary Syndrome (PCOS) include hormone blood tests, pelvic ultrasound, and tests for insulin or glucose levels."
        ],
        "see a doctor": [
            "You should see a doctor if you have irregular periods, excessive hair growth, acne, or difficulty getting pregnant, as these may be signs of Polycystic Ovary Syndrome."
        ],
        "foods should i eat": [
            "For managing Polycystic Ovary Syndrome, it is recommended to eat whole grains, fruits, vegetables, lean proteins, and high-fiber foods."
        ],
        "foods should i avoid": [
            "People with Polycystic Ovary Syndrome should limit sugary foods, refined carbohydrates, fried foods, and highly processed foods."
        ],
        "exercise is best": [
            "Regular exercise such as walking, yoga, strength training, and cardio workouts can help manage Polycystic Ovary Syndrome symptoms."
        ],
        "stress affect pcos": [
            "Stress does not directly cause Polycystic Ovary Syndrome, but it can worsen hormonal imbalance and symptoms."
        ],
        "poor mental health affect pcos": [
            "Yes, stress and poor mental health can worsen the symptoms of Polycystic Ovary Syndrome (PCOS) by affecting hormone balance, sleep, and lifestyle habits."
        ],
        "be cured": [
            "There is no permanent cure for Polycystic Ovary Syndrome, but its symptoms can be effectively managed with treatment and lifestyle changes."
        ],
        "be managed": [
            "Polycystic Ovary Syndrome can be managed through healthy diet, regular exercise, weight management, stress control, and medical treatment if needed."
        ],
        "manage pcos": [
            "Polycystic Ovary Syndrome can be managed through healthy diet, regular exercise, weight management, stress control, and medical treatment if needed."
        ],
        "medicines for pcos": [
            "Yes, doctors may prescribe medicines such as hormonal treatments or medications to regulate periods and manage symptoms of Polycystic Ovary Syndrome."
        ],
        "lifestyle changes": [
            "Yes, healthy lifestyle changes like balanced diet, regular exercise, proper sleep, and stress management can significantly improve Polycystic Ovary Syndrome symptoms."
        ],
        "normal life": [
            "Yes, many people with Polycystic Ovary Syndrome live normal and healthy lives with proper management and medical guidance."
        ],
        "affect pregnancy": [
            "Yes, Polycystic Ovary Syndrome can make pregnancy more difficult due to irregular ovulation, but many women with PCOS can still conceive with treatment."
        ],
        "control pcos naturally": [
            "Polycystic Ovary Syndrome can be naturally managed through healthy diet, regular exercise, maintaining a healthy weight, proper sleep, and stress reduction."
        ],
        "worsen or affect mental health": [
            "Yes, Polycystic Ovary Syndrome (PCOS) can affect mental health. Hormonal changes and symptoms like weight gain, acne, and irregular periods may increase the risk of stress, anxiety, and depression."
        ],
        "affect mood": [
            "Yes, Polycystic Ovary Syndrome can affect mood due to hormonal imbalance, which may lead to mood swings, irritability, or emotional changes."
        ],
        "cause anxiety": [
            "Yes, some people with Polycystic Ovary Syndrome may experience anxiety because of hormonal changes and stress related to symptoms."
        ],
        "lead to depression": [
            "Yes, people with Polycystic Ovary Syndrome may have a higher risk of depression due to hormonal imbalance and physical symptoms."
        ],
        "affect confidence": [
            "Yes, symptoms of Polycystic Ovary Syndrome such as acne, weight gain, or hair growth may affect self-confidence and body image."
        ],
        "self-esteem": [
            "Yes, symptoms of Polycystic Ovary Syndrome such as acne, weight gain, or hair growth may affect self-confidence and body image."
        ],
        "cause irritability": [
            "Yes, hormonal changes in Polycystic Ovary Syndrome may lead to irritability or stronger emotional reactions in some people."
        ],
        "emotional reactions": [
            "Yes, hormonal changes in Polycystic Ovary Syndrome may lead to irritability or stronger emotional reactions in some people."
        ],
        "affect daily behavior": [
            "Yes, symptoms of Polycystic Ovary Syndrome and mental stress may affect motivation, energy levels, and daily habits."
        ],
        "affect decision-making": [
            "Yes, stress related to Polycystic Ovary Syndrome may affect focus, concentration, and decision-making in some individuals."
        ],
        "managing mental health improve pcos": [
            "Yes, stress management techniques such as exercise, meditation, and proper sleep may help improve symptoms of Polycystic Ovary Syndrome."
        ],
        "relaxation techniques": [
            "Yes, activities like yoga, meditation, and breathing exercises can help reduce stress and support management of Polycystic Ovary Syndrome."
        ],
        "pcos": [
            "PCOS (Polycystic Ovary Syndrome) is a hormonal imbalance that many women navigate. You're definitely not alone! It often involves irregular periods and insulin resistance. How can I help you manage it today?",
            "I understand PCOS can be frustrating. It affects 1 in 10 women and can impact your skin, hair, and energy. A good diet is a powerful step towards feeling better! 🌿",
            "Think of PCOS as your body's way of asking for a little extra care. Focusing on Low GI foods and gentle movement can make such a big difference!"
        ],
        "insulin": [
            "High insulin levels can feel like an uphill battle, especially with weight. I recommend focusing on fiber-rich greens and lean proteins. Have you tried our 'Insulin Resistance' diet guide? 🥗",
            "Insulin resistance is very common with PCOS. It's not your fault! Reducing processed sugars and adding healthy fats can help stabilize your energy.",
            "That's a great question. Balancing insulin is key. Try pairing carbs with protein to avoid those spikes!"
        ],
        "diet": [
            "A PCOS-friendly diet is all about balance, not restriction! 🥑 Leafy greens, healthy fats, and low-sugar fruits are your best friends.",
            "I love talking about food! Focus on 'anti-inflammatory' options like berries, walnuts, and fatty fish. They help keep those hormones happy.",
            "A good rule of thumb: If it's colorful and whole, it's probably great for PCOS! Avoid refined carbs where you can."
        ],
        "hello": [
            "Hi there! I'm so happy to see you. How is your wellness journey going today? ✨",
            "Hello! I've been waiting for you. Ready to check in on your health goals?",
            "Greetings! I'm your PCOS assistant. I'm here to listen and help. What's on your mind?"
        ],
        "how are you": [
            "I'm doing wonderfully, thank you for asking! I'm always at my best when I'm helping you. How are *you* feeling today?",
            "I'm feeling very botanical today! 🌿 Ready and eager to help you navigate PCOS. How have you been?",
            "That's so kind of you to ask! I'm powered up and ready to support you. Is everything okay with your health today?"
        ],
        "thanks": [
            "You are so welcome! I'm always here for you. 💚",
            "Anytime! I'm glad I could help. Don't hesitate to ask more.",
            "It's my pleasure! We're in this together."
        ],
        "good": [
            "I'm so glad to hear that! Keep up that positive energy. ✨",
            "That's wonderful! Hearing that you're doing well makes my day.",
            "Awesome! Let's keep that momentum going."
        ],
        "how to use": [
            "It's super simple! Just head to the home page, fill in your details (like Age and Symptoms), and click 'Get My Diet'. I'll handle the rest! 🪄",
            "I can guide you! First, fill out the assessment form. Once you submit, I'll use my ML model to pick the best diet for you. You can find your past results in your Profile!",
            "Just follow the form on the main page. It asks about your lifestyle and symptoms so I can give you the most accurate advice possible."
        ],
        "app": [
            "I'm part of the PCOS Wellness platform! I use a smart Decision Tree model to analyze your health profile and recommend nutrition plans that actually work for PCOS.",
            "This app is designed to be your companion in managing PCOS. From diet mapping to history tracking, we've got everything you need to feel your best! 🌿",
            "We focus on personalized wellness. No 'one-size-fits-all' here—only recommendations tailored specifically to your body and symptoms."
        ],
        "symptoms": [
            "I know symptoms like acne or irregular periods can be tough. Our assessment helps identify your specific needs so we can target them with nutrition. Want to try it?",
            "PCOS symptoms vary for everyone, but we cover the big ones like hirsutism, weight gain, and cycle duration. Let's see what fits you!",
            "It's important to track those symptoms. Have you noticed any changes lately?"
        ],
        "help": [
            "I can help with quite a bit! Ask me 'How to use the app', 'What foods should I eat?', or even just tell me how you're feeling. I'm a good listener! 😊",
            "Need a hand? I can explain PCOS, guide you through the assessment, or help you understand your profile history.",
            "I'm here for whatever you need. Whether it's medical info or just a 'hello', I've got you covered."
        ]
    }
    
    reply = "I'm not exactly sure how to answer that, but I'm learning every day! Try asking about PCOS, diet, or how to use the app. 😊"
    
    # Search for keywords and pick a random response from the list
    for key, val_list in responses.items():
        if key in user_msg:
            reply = random.choice(val_list)
            break
            
    return {"reply": reply}

if __name__ == '__main__':


    app.run(debug=True)
