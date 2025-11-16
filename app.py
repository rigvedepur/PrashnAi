# app.py
# Dash + Plotly interactive quiz app that reads plain-text files like the example provided
# Run:  python app.py
# Then open the printed http://127.0.0.1:8050
# Optional: set QUIZ_DIR env var to a folder containing .txt files to auto-populate the quiz picker.

import os
import re
import io
import json
import base64
from datetime import datetime

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback_context, no_update, ctx

############################
# Parsing & Utilities
############################

QA_BLOCK_RE = re.compile(r"(?ms)^Q\s*(\d+)\s*:\s*(.*?)\n\s*A\)\s*(.*?)\n\s*B\)\s*(.*?)\n\s*C\)\s*(.*?)\n\s*D\)\s*(.*?)\n\s*Answer\s*:\s*([ABCD])\s*$")
# Supports lines like: Q1: text (variant x-y) — but we only use the stem; variant is ignored


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_stem(stem: str) -> str:
    # Remove parenthetical variant tags and collapse whitespace
    stem = re.sub(r"\(variant[^\)]*\)", "", stem, flags=re.IGNORECASE)
    return clean_text(stem)


def parse_quiz_text(text: str, dedupe=True):
    """Parse quiz text into a list of question dicts.
    Expected format blocks like in the user's example.
    """
    blocks = []
    # Split by blank lines that start a new question Qn:
    # A stricter approach: find all QA blocks by regex scanning.
    for match in QA_BLOCK_RE.finditer(text):
        qnum = match.group(1)
        stem_raw = match.group(2)
        A, B, C, D = (match.group(3), match.group(4), match.group(5), match.group(6))
        ans = match.group(7).upper()
        stem = normalize_stem(stem_raw)
        block = {
            "qnum": int(qnum),
            "stem": stem,
            "stem_raw": clean_text(stem_raw),
            "options": {"A": clean_text(A), "B": clean_text(B), "C": clean_text(C), "D": clean_text(D)},
            "answer": ans,
        }
        blocks.append(block)

    if not blocks:
        # Try to be forgiving: chunk by 'Q' lines and rescan inside chunks
        chunks = re.split(r"(?m)^(?=Q\s*\d+\s*:)", text)
        for ch in chunks:
            m = QA_BLOCK_RE.search(ch)
            if m:
                qnum = m.group(1)
                stem_raw = m.group(2)
                A, B, C, D = (m.group(3), m.group(4), m.group(5), m.group(6))
                ans = m.group(7).upper()
                stem = normalize_stem(stem_raw)
                blocks.append({
                    "qnum": int(qnum),
                    "stem": stem,
                    "stem_raw": clean_text(stem_raw),
                    "options": {"A": clean_text(A), "B": clean_text(B), "C": clean_text(C), "D": clean_text(D)},
                    "answer": ans,
                })

    if dedupe:
        seen = set()
        deduped = []
        for b in blocks:
            key = b["stem"].lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(b)
        blocks = deduped

    # Sort by qnum for stable order
    blocks.sort(key=lambda x: x.get("qnum", 0))
    return blocks


def list_quiz_files():
    quiz_dir = os.environ.get("QUIZ_DIR", "")
    items = []
    print(f"QUIZ_DIR environment variable: {quiz_dir}")
    if quiz_dir and os.path.isdir(quiz_dir):
        files = os.listdir(quiz_dir)
        print(f"Files found in QUIZ_DIR: {files}")
        for fn in sorted(files):
            if fn.lower().endswith(".txt"):
                full_path = os.path.join(quiz_dir, fn)
                items.append({"label": fn, "value": full_path})
                print(f"Added to dropdown: {fn} -> {full_path}")
    else:
        print(f"QUIZ_DIR not found or not a directory: {quiz_dir}")
    print(f"Dropdown options: {items}")
    return items


############################
# Default sample for quick start
############################

SAMPLE_TEXT = """Q1: Which mineral primarily strengthens bone? (variant 4-7)
A) Sodium
B) Calcium
C) Potassium
D) Iron
Answer: B

Q2: Rising T3 / T4 typically causes pituitary TSH to: (variant 10-8)
A) Increase
B) Decrease
C) No change
D) Oscillate
Answer: B

Q3: Which ion binds troponin to initiate contraction? (variant 6-2)
A) Na+
B) K+
C) Ca2+
D) Cl-
Answer: C

Q4: Rising T3 / T4 typically causes pituitary TSH to: (variant 10-14)
A) Increase
B) Decrease
C) No change
D) Oscillate
Answer: B

Q5: Which ion binds troponin to initiate contraction? (variant 6-12)
A) Na+
B) K+
C) Ca2+
D) Cl-
Answer: C
"""

DEFAULT_QUESTIONS = parse_quiz_text(SAMPLE_TEXT, dedupe=True)

############################
# Dash App
############################

external_scripts = []
app = Dash(__name__, suppress_callback_exceptions=True, external_scripts=external_scripts)
server = app.server

# Don't call list_quiz_files() at import time - it will be called by the callback
quiz_file_options = []

app.layout = html.Div([
    html.H1("Interactive Quiz (Plotly Dash)"),
    html.Div([
        html.Div([
            html.H3("Quiz Source"),
            dcc.Dropdown(
                id="file-dropdown",
                options=quiz_file_options,
                placeholder="Select a .txt from QUIZ_DIR (optional)",
                clearable=True,
            ),
            html.Div("Or upload a .txt file:"),
            dcc.Upload(
                id="upload",
                children=html.Div(["Drag & Drop or ", html.A("Select File")]),
                multiple=False,
                accept=".txt",
                style={
                    "width": "100%",
                    "height": "60px",
                    "lineHeight": "60px",
                    "borderWidth": "1px",
                    "borderStyle": "dashed",
                    "borderRadius": "5px",
                    "textAlign": "center",
                    "margin": "10px 0",
                },
            ),
            html.Label([
                dcc.Checklist(
                    id="dedupe",
                    options=[{"label": " Deduplicate repeated stems", "value": "on"}],
                    value=["on"],
                    style={"marginTop": "10px"},
                )
            ]),
            html.Label([
                dcc.Checklist(
                    id="shuffle",
                    options=[{"label": " Shuffle questions", "value": "on"}],
                    value=["on"],
                    style={"marginTop": "5px"},
                )
            ]),
            html.Button("Load Quiz", id="load-btn", n_clicks=0, style={"marginTop": "10px"}),
            html.Button("Reset", id="reset-btn", n_clicks=0, style={"marginLeft": "8px"}),
            html.Button("Load Default Questions", id="load-default-btn", n_clicks=0, style={"marginLeft": "8px", "backgroundColor": "#4CAF50", "color": "white"}),
            html.Div(id="file-status", children="Using default questions", style={"marginTop": "10px", "fontSize": "14px", "color": "blue"}),
            html.Hr(),
            html.H3("Results"),
            dcc.Graph(id="score-pie", style={"height": "280px"}),
            dcc.Graph(id="running-accuracy", style={"height": "280px"}),
            html.Button("Download Results (CSV)", id="dl-btn"),
            dcc.Download(id="download-csv"),
        ], style={"flex": "1", "minWidth": 320, "paddingRight": "16px", "borderRight": "1px solid #ddd"}),

        html.Div([
            html.H3("Question"),
            html.Div(id="question-text", style={"fontSize": "20px", "minHeight": "120px"}),
            dcc.RadioItems(id="choices", options=[], value=None, labelStyle={"display": "block", "padding": "6px 0"}),
            html.Div(id="feedback", style={"minHeight": "28px", "fontWeight": "bold", "marginTop": "6px"}),
            html.Div([
                html.Button("Submit", id="submit-btn", n_clicks=0),
                html.Button("Reveal", id="reveal-btn", n_clicks=0, style={"marginLeft": "8px"}),
                html.Button("Next", id="next-btn", n_clicks=0, style={"marginLeft": "8px"}),
            ], style={"marginTop": "8px"}),
            html.Hr(),
            html.Div(id="progress"),
        ], style={"flex": "2", "paddingLeft": "16px"}),
    ], style={"display": "flex", "gap": "16px"}),

    # Hidden stores for state
    dcc.Store(id="store-questions"),
    dcc.Store(id="store-order"),
    dcc.Store(id="store-index", data=0),
    dcc.Store(id="store-history", data=[]),  # list of {idx, chosen, correct(bool)} in order answered
])

############################
# Callbacks
############################


def decode_upload(contents):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    return decoded.decode('utf-8', errors='ignore')


@app.callback(
    Output("store-questions", "data"),
    Output("store-order", "data"),
    Output("store-index", "data"),
    Output("store-history", "data"),
    Output("file-status", "children"),
    Input("load-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    Input("load-default-btn", "n_clicks"),
    Input("upload", "contents"),
    Input("file-dropdown", "value"),
    State("dedupe", "value"),
    State("shuffle", "value"),
    prevent_initial_call=False,
)

def load_or_reset(load_clicks, reset_clicks, load_default_clicks, upload_contents, file_path, dedupe_val, shuffle_val):
    trigger = (callback_context.triggered[0]['prop_id'] if callback_context.triggered else '')
    print(f"load_or_reset called with trigger: {trigger}")
    print(f"callback_context.triggered: {callback_context.triggered}")
    print(f"file_path: {file_path}, upload_contents: {bool(upload_contents)}")

    dedupe = (dedupe_val or []) and ("on" in dedupe_val)
    shuffle_opt = (shuffle_val or []) and ("on" in shuffle_val)

    # Reset to defaults
    if 'reset-btn' in trigger or 'load-default-btn' in trigger:
        q = DEFAULT_QUESTIONS
        status = "Loaded default questions"
    else:
        text = None
        status = ""
        if upload_contents and 'upload' in trigger:
            # File was uploaded
            try:
                text = decode_upload(upload_contents)
                status = "✅ Successfully loaded uploaded file"
                print(f"Successfully loaded uploaded file")
            except Exception as e:
                status = f"❌ Error decoding upload: {e}"
                print(f"Error decoding upload: {e}")
                text = None
        elif file_path and ('file-dropdown' in trigger or 'load-btn' in trigger) and os.path.exists(file_path):
            # File was selected from dropdown (either directly or via load button)
            try:
                with io.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                status = f"✅ Successfully loaded file: {os.path.basename(file_path)}"
                print(f"Successfully loaded file: {file_path}")
            except Exception as e:
                status = f"❌ Error reading file: {e}"
                print(f"Error reading file {file_path}: {e}")
                text = None
        elif 'load-btn' in trigger:
            # Load button clicked but no file selected - use defaults
            text = None
            status = "Using default questions (no file selected)"
        else:
            # Initial load or any other case - use defaults
            text = None
            status = "Using default questions"
        
        if text:
            q = parse_quiz_text(text, dedupe=dedupe)
            status += f" - Parsed {len(q)} questions"
            print(f"Parsed {len(q)} questions from file")
        else:
            q = DEFAULT_QUESTIONS
            if not status:
                status = "Using default questions"
            print("Using default questions")

    # Build order
    order = list(range(len(q)))
    if shuffle_opt:
        import random
        random.Random(42).shuffle(order)  # deterministic shuffle for reproducibility

    print(f"Returning {len(q)} questions, order length: {len(order)}, status: {status}")
    return q, order, 0, [], status


@app.callback(
    Output("question-text", "children"),
    Output("choices", "options"),
    Output("choices", "value"),
    Output("progress", "children"),
    Input("store-questions", "data"),
    Input("store-order", "data"),
    Input("store-index", "data"),
)

def display_question(questions, order, idx):
    print(f"display_question called: questions={len(questions) if questions else 0}, order={len(order) if order else 0}, idx={idx}")
    
    if not questions:
        print("No questions loaded - returning default message")
        return "No questions loaded. Please select a file or click 'Load Quiz' to use default questions.", [], None, ""
    if idx >= len(order):
        return "🎉 Quiz Complete! 🎉", [], None, f"Completed {len(order)} of {len(order)} questions"

    q = questions[order[idx]]
    stem = q["stem"]
    opts = q["options"]
    options = [
        {"label": f"A) {opts['A']}", "value": "A"},
        {"label": f"B) {opts['B']}", "value": "B"},
        {"label": f"C) {opts['C']}", "value": "C"},
        {"label": f"D) {opts['D']}", "value": "D"},
    ]
    progress = f"Question {idx+1} of {len(order)}"
    print(f"Displaying question: {stem[:50]}...")
    return stem, options, None, progress


@app.callback(
    Output("feedback", "children"),
    Output("feedback", "style"),
    Output("store-history", "data"),   # primary
    Output("store-index", "data"),     # primary
    Input("submit-btn", "n_clicks"),
    Input("next-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    State("store-history", "data"),
    State("store-index", "data"),
    State("store-questions", "data"),
    State("store-order", "data"),
    State("choices", "value"),
    prevent_initial_call=True,
)
def main_update(submit_clicks, next_clicks, reset_clicks, history, index, questions, order, chosen):
    trigger = ctx.triggered_id
    if trigger == "submit-btn":
        if not chosen or not questions or not order or index is None:
            return "Please select an answer first", {"color": "red"}, history, index
        
        current_q = questions[order[index]]
        correct_answer = current_q["answer"]
        is_correct = chosen == correct_answer
        
        # Add to history
        new_history = (history or []) + [{
            "idx": index,
            "q_idx": order[index],
            "chosen": chosen,
            "correct": is_correct
        }]
        
        if is_correct:
            feedback = f"Correct! The answer is {correct_answer}"
            style = {"color": "green"}
        else:
            feedback = f"Incorrect. The correct answer is {correct_answer}"
            style = {"color": "red"}
        
        return feedback, style, new_history, index
    
    elif trigger == "next-btn":
        new_index = (index or 0) + 1
        return no_update, no_update, history, new_index
    
    elif trigger == "reset-btn":
        return "Reset", {"color": "green"}, [], 0
    
    return no_update, no_update, no_update, no_update

@app.callback(
    Output("feedback", "children", allow_duplicate=True),
    Output("feedback", "style", allow_duplicate=True),
    Input("reveal-btn", "n_clicks"),
    State("store-questions", "data"),
    State("store-order", "data"),
    State("store-index", "data"),
    prevent_initial_call=True,
)
def reveal_answer(reveal_clicks, questions, order, index):
    if not questions or not order or index is None or index >= len(order):
        return "No question to reveal", {"color": "gray"}
    
    current_q = questions[order[index]]
    correct_answer = current_q["answer"]
    feedback = f"The correct answer is {correct_answer}: {current_q['options'][correct_answer]}"
    style = {"color": "blue", "fontWeight": "bold"}
    
    return feedback, style


@app.callback(
    Output("file-dropdown", "options"),
    Input("file-dropdown", "id"),
    prevent_initial_call=False,
)
def update_dropdown_options(_):
    """Update dropdown options when the app loads"""
    print("Updating dropdown options...")
    options = list_quiz_files()
    print(f"Dropdown updated with {len(options)} options")
    return options

# Also add a callback to refresh dropdown when app starts
@app.callback(
    Output("file-dropdown", "options", allow_duplicate=True),
    Input("load-btn", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_dropdown_on_load(_):
    """Refresh dropdown when load button is clicked"""
    print("Refreshing dropdown options...")
    return list_quiz_files()


@app.callback(
    Output("feedback", "children", allow_duplicate=True),
    Output("feedback", "style", allow_duplicate=True),
    Input("next-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_feedback_on_next(_):
    return "", {"color": "black"}

@app.callback(
    Output("score-pie", "figure"),
    Output("running-accuracy", "figure"),
    Input("store-history", "data"),
    Input("store-order", "data"),
)

def update_charts(history, order):
    total_answered = len(history or [])
    correct = sum(1 for h in (history or []) if h["correct"])
    incorrect = total_answered - correct

    # Pie chart - handle empty state
    if total_answered == 0:
        pie = go.Figure(go.Pie(labels=["No answers yet"], values=[1], hole=0.5))
        pie.update_layout(margin=dict(l=10, r=10, t=30, b=10), title="Score: 0/0")
    else:
        pie = go.Figure(go.Pie(labels=["Correct", "Incorrect"], values=[correct, incorrect], hole=0.5))
        pie.update_layout(margin=dict(l=10, r=10, t=30, b=10), title=f"Score: {correct}/{total_answered}")

    # Running accuracy line - handle empty state
    if total_answered == 0:
        line = go.Figure()
        line.update_layout(
            margin=dict(l=10, r=10, t=30, b=40), 
            title="Running Accuracy (%)", 
            xaxis_title="Attempt #", 
            yaxis_title="%",
            annotations=[dict(text="No answers yet", x=0.5, y=0.5, showarrow=False)]
        )
    else:
        acc_y = []
        running = 0
        for i, h in enumerate(history):
            running += 1 if h["correct"] else 0
            acc_y.append(100.0 * running / (i + 1))
        line = go.Figure(go.Scatter(y=acc_y, mode="lines+markers"))
        line.update_layout(margin=dict(l=10, r=10, t=30, b=40), title="Running Accuracy (%)", xaxis_title="Attempt #", yaxis_title="%")

    return pie, line


@app.callback(
    Output("download-csv", "data"),
    Input("dl-btn", "n_clicks"),
    State("store-history", "data"),
    State("store-questions", "data"),
    prevent_initial_call=True,
)

def download_results(n, history, questions):
    if not history:
        return no_update
    # Build CSV
    rows = ["attempt,question,chosen,correct,answer"]
    for i, h in enumerate(history, start=1):
        q = questions[h["q_idx"]]
        rows.append(
            ",".join([
                str(i),
                '"' + q["stem"].replace('"', '""') + '"',
                h.get("chosen", ""),
                "TRUE" if h.get("correct") else "FALSE",
                q.get("answer", ""),
            ])
        )
    csv_str = "\n".join(rows)
    fname = f"quiz_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return dict(content=csv_str, filename=fname)


if __name__ == "__main__":
    app.run(debug=True)