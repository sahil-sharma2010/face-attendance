import cv2
import os
import sqlite3
import sys
from datetime import datetime

# ==========================================
# 🔥 STRICTNESS SETTING (YAHAN SE CONTROL KAREIN) 🔥
# ==========================================
# Isko 40 se 60 ke beech rakhein.
# Jitna chota number hoga, checking utni SAKHT (Strict) hogi.
STRICTNESS_THRESHOLD = 45 

# ==========================================
# 1. GET DATA FROM PORTAL
# ==========================================
if len(sys.argv) < 4:
    print("MISMATCH")
    sys.exit()

expected_name = str(sys.argv[1]).strip().lower()
expected_roll = str(sys.argv[2]).strip()
subject = str(sys.argv[3]).strip()

# ==========================================
# 2. LOAD MODEL & CASCADES
# ==========================================
recognizer = cv2.face.LBPHFaceRecognizer_create()
if not os.path.exists('trainer.yml'):
    print("MISMATCH")
    sys.exit()

recognizer.read('trainer.yml')
faceCascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
eyeCascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml')

# ==========================================
# 3. LOAD NAMES
# ==========================================
names = {}
if os.path.exists('labels.txt'):
    with open('labels.txt', 'r') as f:
        for i, line in enumerate(f.readlines()):
            names[i] = line.strip().split(',')[-1]
else:
    dataset_dir = 'static/dataset'
    if os.path.exists(dataset_dir):
        for i, name in enumerate(sorted(os.listdir(dataset_dir))):
            names[i] = name

# ==========================================
# 4. START CAMERA & ULTIMATE LOGIC
# ==========================================
cam = cv2.VideoCapture(0)
cam.set(3, 640)
cam.set(4, 480)
font = cv2.FONT_HERSHEY_SIMPLEX

mismatch_timer = 0
blink_counter = 0
attendance_marked = False

# 🔥 NAYA CODE: VOTING HISTORY ARRAY ADD KIYA 🔥
prediction_history = [] 

while True:
    ret, img = cam.read()
    if not ret: break

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = faceCascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))

    if len(faces) == 0:
        cv2.putText(img, "FACE NOT FOUND", (20, 40), font, 0.8, (0, 0, 255), 2)
        mismatch_timer += 1

    for (x, y, w, h) in faces:
        id_num, confidence = recognizer.predict(gray[y:y+h, x:x+w])

        # 🔥 YAHAN MAIN CHECKING HOTI HAI 🔥
        if confidence < STRICTNESS_THRESHOLD: 
            raw_name = names.get(id_num, "Unknown")
            
            if raw_name != "Unknown":
                if "_" in raw_name:
                    db_name = raw_name.split("_")[0].strip().lower()
                    student_roll = raw_name.split("_")[1]
                else:
                    db_name = raw_name.strip().lower()
                    student_roll = "N/A"

                # 🔥 NAYA CODE: History mein face ka naam add karo (Voting logic) 🔥
                prediction_history.append(db_name)
                if len(prediction_history) > 20:
                    prediction_history.pop(0) # Sirf last 20 frames yaad rakho
                    
                match_count = prediction_history.count(expected_name)

                if db_name == expected_name:
                    mismatch_timer = 0 # Sahi face hai
                    
                    # BLINK DETECTION (Aapka purana logic waise ka waisa)
                    roi_gray = gray[y:y+h, x:x+w]
                    eyes = eyeCascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(15, 15))
                    
                    if len(eyes) == 0:
                        blink_counter += 1 # Aankhein band hui
                    
                    if blink_counter > 2:
                        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        
                        # ✅ VOTING SYSTEM: 20 mein se 15 baar verify hona chahiye
                        cv2.putText(img, f"VERIFYING... {match_count}/15", (x+5, y-10), font, 0.8, (0, 255, 0), 2)
                        
                        if match_count >= 15:
                            now = datetime.now()
                            date_str = now.strftime("%Y-%m-%d")
                            time_str = now.strftime("%H:%M:%S")
                            
                            conn = sqlite3.connect("attendance.db")
                            cursor = conn.cursor()
                            cursor.execute("SELECT * FROM attendance WHERE name=? AND date=? AND subject=?", (db_name.upper(), date_str, subject))
                            if not cursor.fetchone():
                                cursor.execute("INSERT INTO attendance (name, roll, subject, date, time) VALUES (?, ?, ?, ?, ?)", 
                                              (db_name.upper(), student_roll, subject, date_str, time_str))
                                conn.commit()
                            conn.close()

                            print("SUCCESS")
                            attendance_marked = True
                            break
                    else:
                        cv2.rectangle(img, (x, y), (x+w, y+h), (255, 165, 0), 2)
                        cv2.putText(img, "PLEASE BLINK", (x+5, y-10), font, 0.8, (0, 165, 255), 2)

                else:
                    mismatch_timer += 1
                    cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 3)
                    cv2.putText(img, f"FAKE: {db_name.upper()}", (x+5, y-10), font, 0.8, (0, 0, 255), 2)
            else:
                mismatch_timer += 1
                cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 2)
                cv2.putText(img, "UNKNOWN FACE", (x+5, y-10), font, 0.8, (0, 0, 255), 2)
        else:
            # Agar Match kamzor hai toh reject
            mismatch_timer += 1
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 2)
            cv2.putText(img, "MATCH FAILED!", (x+5, y-10), font, 0.8, (0, 0, 255), 2)

    if attendance_marked:
        break
        
    # Agar 40 frames tak lagatar reject hua, Camera Mismatch dekar Fail ho jayega
    if mismatch_timer >= 40: 
        print("MISMATCH")
        break

    cv2.imshow("ULTIMATE STRICT VERIFICATION", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()