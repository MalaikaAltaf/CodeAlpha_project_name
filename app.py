import sys
sys.path.append(r"C:\Users\hp\AppData\Local\Programs\Python\Python312\Lib\site-packages")
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_mysqldb import MySQL
import MySQLdb.cursors
import os

# AI Tools Imports
from ai_integration.grade_model import GradeModel
from ai_integration.essay_grading import EssayGrader
from ai_integration.sentiment_analysis import SentimentAnalysis
from ai_integration.feature_extractor import FeatureExtractor

from config import DevelopmentConfig

# Initialize Flask app and load configuration
app = Flask(__name__)
app.config.from_object(DevelopmentConfig)  # Load development configuration

# Initialize MySQL
mysql = MySQL(app)

# Initialize AI Tools
grade_model = GradeModel(model_path=app.config['GRADE_MODEL_PATH'])
essay_grader = EssayGrader(reference_text="This is the sample reference essay.")  # Default reference
sentiment_analyzer = SentimentAnalysis()
feature_extractor = FeatureExtractor()

# ------------------ ROUTES ------------------

# Home route (redirect to login)
@app.route('/')
def home():
    return redirect(url_for('login'))


# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", (username, password, role))
        mysql.connection.commit()
        cur.close()

        flash("User registered successfully.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')


# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    show_signup = False
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()

        if user and user['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user['role']

            flash("Login successful!", "success")
            return redirect(url_for('teacher_dashboard') if user['role'] == 'teacher' else url_for('student_dashboard'))
        else:
            flash("Invalid username or password.", "error")
    return render_template('login.html', show_signup=show_signup)


# Teacher Dashboard Route
@app.route('/teacher_dashboard', methods=['GET', 'POST'])
def teacher_dashboard():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    if request.method == 'POST':
        student_name = request.form.get('student_name')
        grading_criteria = request.form.get('grading_criteria')
        assignment_file = request.files['assignment_file']

        if assignment_file:
            # Save uploaded file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], assignment_file.filename)
            assignment_file.save(file_path)

            # Read and preprocess essay content
            with open(file_path, 'rb') as file:
                submitted_essay = file.read().decode('utf-8', errors='ignore')

            # AI Tools: Grading, Similarity, Sentiment
            predicted_grade = grade_model.predict_grade(submitted_essay)
            similarity_score = essay_grader.calculate_similarity(submitted_essay)
            sentiment = sentiment_analyzer.analyze_sentiment(submitted_essay)

            # Extract additional features
            features = feature_extractor.extract_features(submitted_essay)

            # Calculate final grade based on similarity and features
            if similarity_score > 0.8:
                final_grade = "A"
            elif similarity_score > 0.5:
                final_grade = "B"
            else:
                final_grade = "C"

            # Save results to database
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO assignments (student_name, teacher_username, assignment_filename,
                                         grade, grading_criteria, automated_score, teacher_feedback)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (student_name, session['username'], assignment_file.filename, final_grade,
                  grading_criteria, similarity_score, f"Sentiment: {sentiment}"))
            mysql.connection.commit()
            cur.close()

            # Flash and redirect
            flash(f"Grade: {final_grade}, Similarity: {similarity_score:.2f}, Sentiment: {sentiment}", "success")
            return redirect(url_for('results', student_name=student_name, grade=final_grade, criteria=grading_criteria))

    return render_template('teacher_dashboard.html')


# Results Route
@app.route('/results')
def results():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    student_name = request.args.get('student_name')
    grade = request.args.get('grade')
    criteria = request.args.get('criteria')

    return render_template('results.html', student_name=student_name, grade=grade, criteria=criteria)


# Student Dashboard Route
@app.route('/student_dashboard')
def student_dashboard():
    if not session.get('logged_in') or session.get('role') != 'student':
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM assignments WHERE student_name = %s", (session['username'],))
    assignments = cur.fetchall()
    cur.close()

    return render_template('student_dashboard.html', assignments=assignments)


# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))


# ------------------ RUN APP ------------------

if __name__ == '__main__':
    app.run(debug=True)
