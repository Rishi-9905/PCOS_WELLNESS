import pandas as pd
import random
import os
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.multioutput import MultiOutputClassifier

# Get the current directory of this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- Load Data ----------
# Using relative paths joined with BASE_DIR for portability
df_map = pd.read_excel(os.path.join(BASE_DIR, "deit_maaping.csv.xlsx"))
df = pd.read_csv(os.path.join(BASE_DIR, "Cleaned-Data.csv"))

# Identify diet columns and binarize
diet_cols = [c for c in df.columns if c.lower().startswith("diet")]
for col in diet_cols:
    df[col] = (df[col] > 0).astype(int)

X_raw = df.drop(columns=diet_cols)
Y = df[diet_cols]
feature_columns = pd.get_dummies(X_raw, drop_first=True).columns

X = pd.get_dummies(X_raw, drop_first=True)
X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2, random_state=42)

clf = MultiOutputClassifier(DecisionTreeClassifier(max_depth=4, random_state=42))
clf.fit(X_train, Y_train)

def preprocess_input(answers):
    """
    Converts raw form inputs into the categorical format expected by the model.
    """
    # 1. Map Age to buckets
    age = answers.get("Age", 0)
    try:
        age_val = float(age)
        if age_val < 20: age_cat = "Less than 20"
        elif 20 <= age_val <= 25: age_cat = "20-25"
        elif 25 < age_val <= 30: age_cat = "25-30"
        elif 30 < age_val <= 35: age_cat = "30-35"
        elif 35 < age_val <= 44: age_cat = "35-44"
        else: age_cat = "45 and above"
        answers["Age"] = age_cat
    except (ValueError, TypeError):
        pass
    
    # 2. Map weight and height to exact CSV keys
    if "Weight" in answers: answers["Weight_kg"] = answers.pop("Weight")
    if "Height" in answers: answers["Height_ft"] = answers.pop("Height") # Dataset says ft but uses cm
    
    # 3. Map Yes/No fields to CSV specific keys
    if "Family_History" in answers:
        answers["Family_History_PCOS"] = answers.pop("Family_History")
    
    if "Regular_Periods" in answers:
        val = answers.pop("Regular_Periods")
        answers["Menstrual_Irregularity"] = "No" if val == "Yes" else "Yes"
    
    if "Skin_Darkening" in answers:
        answers["Insulin_Resistance"] = answers.get("Skin_Darkening") # Common proxy in this dataset
        
    return answers


# ---------- User Q & A ----------
if __name__ == "__main__":
    print("\n--- Please answer a few questions for your personalised diet ---")
    answers = {}
    answers["Age"] = int(input("Age (years): "))
    answers["Weight"] = float(input("Weight (kg): "))
    answers["Height"] = float(input("Height (cm): "))
    answers["Exercise_Level"] = input("Exercise level (None/Low/Moderate/High): ")
    answers["Region"] = input("Region (Urban/Rural): ")
    answers["Stress_Level"] = input("Stress level (Low/Medium/High): ")
    answers["Sleep_Hours"] = float(input("Average sleep per night (hours): "))
    answers["Sugar_Intake"] = input("Daily sugar intake (Low/Medium/High): ")
    answers["Diet_Type"] = input("Food preference (Vegetarian/Vegan/Non-Vegetarian): ").strip().lower()

    # allergies and dislikes
    allergies_input = input(
        "List any allergies (comma separated, e.g. peanut, soy, milk, nuts). If none, press Enter: "
    ).strip().lower()
    allergies = [a.strip() for a in allergies_input.split(",") if a.strip()]

    answers["Regular_Periods"] = input("Are your menstrual cycles regular? (Yes/No): ")
    answers["Cycle_Length"] = float(input("Average menstrual cycle length in days: "))
    answers["Duration_Menstruation"] = float(input("How many days does your period usually last? "))
    answers["Pregnancies"] = int(input("Number of pregnancies: "))
    answers["Weight_Gain"] = input("Recent weight gain? (Yes/No): ")
    answers["Hair_Growth"] = input("Excess facial/body hair? (Yes/No): ")
    answers["Acne"] = input("Do you often have acne breakouts? (Yes/No): ")
    answers["Skin_Darkening"] = input("Any skin darkening (neck/armpits)? (Yes/No): ")
    answers["Hair_Loss"] = input("Unusual scalp hair loss? (Yes/No): ")
    answers["Family_History"] = input("Family history of PCOS/Diabetes? (Yes/No): ")
    answers["Smoking"] = input("Do you smoke? (Yes/No): ")
    answers["Alcohol"] = input("Do you drink alcohol? (Yes/No): ")

    insulin = input("Recent fasting insulin level (if known, else press Enter): ")
    answers["Insulin_Level"] = float(insulin) if insulin else 0.0

    dislikes_input = input(
        "List any foods you do NOT want (comma-separated, leave blank if none): "
    ).strip().lower()
    disliked_items = [d.strip() for d in dislikes_input.split(",") if d.strip()]

    # ---------- Prepare Input ----------
    new_df = pd.DataFrame([answers])
    new_df_encoded = pd.get_dummies(new_df, drop_first=True)
    new_df_encoded = new_df_encoded.reindex(columns=feature_columns, fill_value=0)
    new_pred = clf.predict(new_df_encoded)[0]

    # ---------- Diet Mapping ----------
    diet_food_map = {
        row["diet_label"]: [str(item).strip() for item in row[1:] if pd.notna(item)]
        for _, row in df_map.iterrows()
    }

    # substitutions dictionary
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

    # diet type filter helper
    def is_allowed(item: str) -> bool:
        lower = item.lower()
        if answers["Diet_Type"] == "vegan" and any(x in lower for x in ["egg", "milk", "cheese", "butter", "ghee", "honey"]):
            return False
        if answers["Diet_Type"] == "vegetarian" and any(x in lower for x in ["chicken", "fish", "meat", "prawn"]):
            return False
        if any(a in lower for a in allergies):
            return False
        return True

    # ---------- Filter & Print ----------
    recommended_foods = {}
    for label, flag in zip(diet_cols, new_pred):
        if flag != 1:
            continue
        safe_foods = []
        for food in diet_food_map[label]:
            f_low = food.lower()
            if not is_allowed(food):
                continue
            if f_low in disliked_items:
                if f_low in substitutions:
                    subs_safe = [s for s in substitutions[f_low] if is_allowed(s)]
                    if subs_safe:
                        safe_foods.append(f"{food} (user dislikes) → Try instead: {', '.join(subs_safe)}")
                    else:
                        safe_foods.append(f"{food} (user dislikes) → No safe substitute available")
                else:
                    safe_foods.append(f"{food} (user dislikes) → No listed substitute")
            else:
                safe_foods.append(food)
        if safe_foods:
            recommended_foods[label] = safe_foods

    print("\nRecommended foods for this person:\n")
    if not recommended_foods:
        print("No specific diet categories were predicted.")
    else:
        mode = input("Quick Pick Mode? Show only ONE item per category? (yes/no): ").strip().lower()
        for category, foods in recommended_foods.items():
            print(f"{category}:")
            if mode == "yes":
                print(f"  - {random.choice(foods)}")
            else:
                for f in foods:
                    print(f"  - {f}")
            print()
