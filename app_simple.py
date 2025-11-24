#!/usr/bin/env python3
"""
PrashnAI Quiz App with Bootstrap UI
"""
import os
import re
import base64
from datetime import datetime

from dash import Dash, dcc, html, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# Set QUIZ_DIR environment variable
QUIZ_DIR = os.path.join(os.path.dirname(__file__), 'QUIZ_DIR')
os.environ['QUIZ_DIR'] = QUIZ_DIR

# Ensure QUIZ_DIR exists
os.makedirs(QUIZ_DIR, exist_ok=True)
print(f"📂 Using quiz directory: {os.path.abspath(QUIZ_DIR)}")
############################
# Parsing & Utilities
############################

QA_BLOCK_RE = re.compile(
    r"(?ms)^(?:Q\s*)?(\d+)\s*(?::|\.)\s*(.*?)\n\s*A\)\s*(.*?)\n\s*B\)\s*(.*?)\n\s*C\)\s*(.*?)\n\s*D\)\s*(.*?)\n\s*Answer\s*:\s*([ABCD])\s*$")



def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def normalize_stem(stem: str) -> str:
    stem = re.sub(r"\(variant[^\)]*\)", "", stem, flags=re.IGNORECASE)
    return clean_text(stem)


def parse_quiz_text(text: str, dedupe=True, max_questions=25):
    """Parse quiz text into a list of question dicts."""
    blocks = []
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
        # Try to be forgiving: chunk by lines that look like question starts in either format
        # Supports:
        #  - Q1: ...
        #  - 1.  ...
        chunks = re.split(r"(?m)^(?=(?:Q\s*)?\d+\s*(?::|\.))", text)
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

    blocks.sort(key=lambda x: x.get("qnum", 0))

    # Limit to max_questions
    if len(blocks) > max_questions:
        blocks = blocks[:max_questions]

    return blocks


def list_quiz_files():
    """Get list of quiz files from QUIZ_DIR"""
    items = []
    try:
        if os.path.isdir(QUIZ_DIR):
            files = os.listdir(QUIZ_DIR)
            if not files:
                print("ℹ️ No quiz files found in the QUIZ_DIR. Please add .txt files to the directory.")
            for fn in sorted(files):
                if fn.lower().endswith(".txt"):
                    full_path = os.path.join(QUIZ_DIR, fn)
                    items.append({"label": fn, "value": full_path})
        else:
            print(f"⚠️ QUIZ_DIR does not exist: {QUIZ_DIR}")
    except Exception as e:
        print(f"❌ Error listing quiz files: {str(e)}")
    return items


def list_topics():
    """Get list of topic folders inside QUIZ_DIR"""
    topics = []
    try:
        if os.path.isdir(QUIZ_DIR):
            for name in sorted(os.listdir(QUIZ_DIR)):
                path = os.path.join(QUIZ_DIR, name)
                if os.path.isdir(path):
                    topics.append({"label": name, "value": path})
    except Exception as e:
        print(f"❌ Error listing topics: {str(e)}")
    return topics


def list_topic_files(topic_path):
    """Get list of .txt quiz files within a topic folder"""
    items = []
    if not topic_path:
        return items
    try:
        if os.path.isdir(topic_path):
            for fn in sorted(os.listdir(topic_path)):
                if fn.lower().endswith(".txt"):
                    full_path = os.path.join(topic_path, fn)
                    items.append({"label": fn, "value": full_path})
    except Exception as e:
        print(f"❌ Error listing files for topic '{topic_path}': {str(e)}")
    return items


def decode_upload(contents):
    """Decode uploaded file contents"""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    return decoded.decode('utf-8', errors='ignore')


def get_random_questions(all_questions, count=25):
    """Get a random selection of questions from all available questions"""
    import random
    if len(all_questions) <= count:
        return all_questions
    return random.sample(all_questions, count)


############################
# Sample Data
############################

SAMPLE_TEXT = """Q1: Which mineral primarily strengthens bone?
A) Sodium
B) Calcium
C) Potassium
D) Iron
Answer: B

Q2: Rising T3 / T4 typically causes pituitary TSH to:
A) Increase
B) Decrease
C) No change
D) Oscillate
Answer: B

Q3: Which ion binds troponin to initiate contraction?
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

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
server = app.server

# Get available files
topics = list_topics()
quiz_files = []

app.layout = dbc.Container(fluid=True, children=[
    # Header
    dbc.Row(
        dbc.Col(
            html.H1("PrashnAI Quiz App", className="text-center my-4 text-primary"),
            width=12
        )
    ),

    # Main content
    dbc.Row([
        # Left sidebar
        dbc.Col(md=4, children=[
            dbc.Card([
                dbc.CardHeader("📁 Quiz Source", className="h5"),
                dbc.CardBody([
                    # Topic selection
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Select a topic:"),
                            dcc.Dropdown(
                                id="topic-dropdown",
                                options=topics,
                                placeholder="Choose a topic folder...",
                                clearable=True,
                                className="mb-3"
                            ),
                        ])
                    ]),

                    # File selection
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Select a quiz file:"),
                            dcc.Dropdown(
                                id="file-dropdown",
                                options=quiz_files,
                                placeholder="Choose a .txt file...",
                                clearable=True,
                                className="mb-3"
                            ),
                        ])
                    ]),

                    # Options
                    dbc.Row([
                        dbc.Col([
                            dbc.Checklist(
                                id="dedupe",
                                options=[{"label": " Remove duplicate questions", "value": "on"}],
                                value=["on"],
                                switch=True,
                                className="mb-2"
                            ),
                            dbc.Checklist(
                                id="shuffle",
                                options=[{"label": " Shuffle questions", "value": "on"}],
                                value=["on"],
                                switch=True,
                                className="mb-3"
                            ),
                        ])
                    ]),
                    # Status
                    dbc.Alert(
                        "Please select a quiz file to begin",
                        id="status",
                        color="light",
                        className="mb-3",
                        style={"wordBreak": "break-word"}
                    ),
                    dbc.Alert(
                        "ℹ️ On file selection, 50 random questions are loaded (or all if fewer than 50).",
                        color="info",
                        className="small p-2 mb-3"
                    ),
                    # Results Section
                    html.Hr(className="my-3"),
                    html.H5("📊 Results", className="mb-3"),
                    dcc.Graph(
                        id="score-chart",
                        style={
                            "height": "300px",
                            "width": "100%",
                            "border": "1px solid #e1e1e1",
                            "borderRadius": "8px",
                            "padding": "10px",
                            "backgroundColor": "white"
                        },
                        config={
                            'displayModeBar': True,
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                            'responsive': True
                        }
                    ),
                    dbc.Button(
                        "📥 Download Results",
                        id="download-btn",
                        color="primary",
                        className="w-100 mt-3"
                    ),
                    dcc.Download(id="download-data"),
                ])
            ], className="h-100")
        ], className="mb-4 mb-md-0"),

        # Right content
        dbc.Col(md=8, children=[
            dbc.Card([
                dbc.CardHeader("❓ Question", className="h5"),
                dbc.CardBody([
                    # Question display
                    dbc.Card(
                        dbc.CardBody(
                            html.Div(
                                id="question-display",
                                className="h4",
                                style={"minHeight": "100px", "wordBreak": "break-word"}
                            )
                        ),
                        className="mb-3"
                    ),

                    # Choices
                    html.Div(id="choices-container", className="mb-3"),

                    # Feedback
                    dbc.Alert(
                        id="feedback",
                        color="light",
                        className="mb-3",
                        style={"display": "none"}
                    ),

                    # Buttons
                    dbc.ButtonGroup([
                        dbc.Button("✅ Submit", id="submit", color="primary", className="me-2"),
                        dbc.Button("➡️ Next", id="next", color="warning")
                    ], className="mb-3"),

                    # Progress
                    html.Div(
                        id="progress",
                        className="text-muted text-end"
                    )
                ])
            ], className="h-100")
        ])
    ], className="g-3")
], style={"maxWidth": "1400px", "padding": "20px"})

# Hidden stores
app.layout.children.extend([
    dcc.Store(id="questions-store", data=[]),
    dcc.Store(id="all-questions-store", data=[]),
    dcc.Store(id="order-store", data=[]),
    dcc.Store(id="index-store", data=0),
    dcc.Store(id="history-store", data=[]),
])


############################
# Callbacks
############################

@app.callback(
    [Output("questions-store", "data"),
     Output("all-questions-store", "data"),
     Output("order-store", "data"),
     Output("index-store", "data"),
     Output("history-store", "data"),
     Output("status", "children"),
     Output("status", "color")],
    [Input("file-dropdown", "value")],
    [State("dedupe", "value"),
     State("shuffle", "value"),
     State("all-questions-store", "data")]
)
def load_quiz(file_path, dedupe, shuffle, all_questions):
    """Load quiz questions from various sources"""
    dedupe_on = dedupe and "on" in dedupe
    shuffle_on = shuffle and "on" in shuffle
    
    if file_path:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            all_questions = parse_quiz_text(text, dedupe=dedupe_on, max_questions=1000)
            questions = get_random_questions(all_questions, 50)  # Load random 50
            status = f"✅ Loaded {len(questions)} random questions from {os.path.basename(file_path)} (source has {len(all_questions)})"
            color = "success"
        except Exception as e:
            questions = DEFAULT_QUESTIONS
            all_questions = DEFAULT_QUESTIONS
            status = f"❌ Error loading file: {str(e)}"
            color = "danger"
    else:
        questions = []
        all_questions = all_questions or []
        status = "ℹ️ Select a quiz file to begin"
        color = "light"

    # Create order
    order = list(range(len(questions)))
    if shuffle_on and questions:
        import random
        random.shuffle(order)

    return questions, all_questions, order, 0, [], status, color


@app.callback(
    [Output("question-display", "children"),
     Output("choices-container", "children"),
     Output("progress", "children")],
    [Input("questions-store", "data"),
     Input("order-store", "data"),
     Input("index-store", "data")]
)
def display_question(questions, order, index):
    """Display the current question"""
    if not questions or not order or index >= len(order):
        return "No questions available", [], ""

    question = questions[order[index]]
    stem = question["stem"]
    options = question["options"]

    choices = dbc.RadioItems(
        id="choices",
        options=[
            {"label": f"A) {options['A']}", "value": "A"},
            {"label": f"B) {options['B']}", "value": "B"},
            {"label": f"C) {options['C']}", "value": "C"},
            {"label": f"D) {options['D']}", "value": "D"},
        ],
        value=None,
        className="mb-3"
    )

    progress = f"Question {index + 1} of {len(order)}"

    return stem, choices, progress


@app.callback(
    [Output("feedback", "children"),
     Output("feedback", "color"),
     Output("feedback", "style"),
     Output("history-store", "data", allow_duplicate=True),
     Output("index-store", "data", allow_duplicate=True)],
    [Input("submit", "n_clicks"),
     Input("next", "n_clicks")],
    [State("choices", "value"),
     State("questions-store", "data"),
     State("order-store", "data"),
     State("index-store", "data"),
     State("history-store", "data")],
    prevent_initial_call=True
)
def handle_actions(submit, next_click, selected, questions, order, index, history):
    """Handle submit, next, and reveal actions"""
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'] if ctx.triggered else None

    if trigger == "submit.n_clicks":
        # Prevent re-submitting the same question: if already in history, return existing feedback
        if history:
            prev = next((h for h in history if h.get("index") == index), None)
            if prev is not None:
                was_correct = prev.get("correct", False)
                answer = prev.get("answer")
                if was_correct:
                    feedback = f"✅ Correct! The answer is {answer}"
                    color = "success"
                else:
                    feedback = f"❌ Incorrect. The correct answer is {answer}"
                    color = "danger"
                return feedback, color, {"display": "block"}, history, index

        if not selected:
            return "Please select an answer first!", "danger", {"display": "block"}, history, index

        question = questions[order[index]]
        correct = selected == question["answer"]

        # Add to history
        new_history = history + [{
            "index": index,
            "question": question["stem"],
            "selected": selected,
            "correct": correct,
            "answer": question["answer"]
        }]

        if correct:
            feedback = f"✅ Correct! The answer is {question['answer']}"
            color = "success"
        else:
            feedback = f"❌ Incorrect. The correct answer is {question['answer']}"
            color = "danger"

        return feedback, color, {"display": "block"}, new_history, index

    elif trigger == "next.n_clicks":
        new_index = min(index + 1, len(order) - 1)
        return "", "light", {"display": "none"}, history, new_index

    return "", "light", {"display": "none"}, history, index


@app.callback(
    [Output("file-dropdown", "options"),
     Output("file-dropdown", "value")],
    [Input("topic-dropdown", "value")]
)
def update_file_options(topic_path):
    """Update file dropdown based on selected topic folder"""
    if not topic_path:
        return [], None
    options = list_topic_files(topic_path)
    return options, None


@app.callback(
    Output("score-chart", "figure"),
    [Input("history-store", "data")]
)
def update_chart(history):
    """Update the score chart"""
    if not history:
        fig = go.Figure()
        fig.add_annotation(
            text="No answers yet",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16)
        )
        fig.update_layout(
            title=dict(
                text="Score Chart",
                font=dict(size=18, color='#2c3e50'),
                x=0.5,
                xanchor='center'
            ),
            xaxis_title="Question",
            yaxis_title="Score",
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=50, t=50, b=50),
            height=300
        )
        return fig

    correct = sum(1 for h in history if h["correct"])
    total = len(history)

    fig = go.Figure(go.Bar(
        x=["Correct", "Incorrect"],
        y=[correct, total - correct],
        marker_color=["#27ae60", "#e74c3c"],
        text=[f"{correct}", f"{total - correct}"],
        textposition='auto',
        textfont=dict(size=14, color='white')
    ))

    fig.update_layout(
        title=dict(
            text=f"Score: {correct}/{total} ({100 * correct / total:.1f}%)",
            font=dict(size=18, color='#2c3e50'),
            x=0.5,
            xanchor='center'
        ),
        xaxis=dict(
            title=dict(text="Result", font=dict(size=14)),
            tickfont=dict(size=14)
        ),
        yaxis=dict(
            title=dict(text="Count", font=dict(size=14)),
            tickfont=dict(size=12),
            gridcolor='#e1e1e1',
            gridwidth=1
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=50, r=50, t=50, b=50),
        height=300,
        hovermode='closest',
        showlegend=False
    )

    # Add value labels on top of bars
    fig.update_traces(
        texttemplate='%{text}',
        textposition='outside',
        textfont_size=16,
        textfont_color='#2c3e50',
        marker_line_color='rgba(0,0,0,0.1)',
        marker_line_width=1.5,
        opacity=0.9
    )
    return fig


@app.callback(
    Output("download-data", "data"),
    [Input("download-btn", "n_clicks")],
    [State("history-store", "data")],
    prevent_initial_call=True
)
def download_results(n_clicks, history):
    """Download results as CSV"""
    if not history:
        return no_update

    csv_content = "Question,Selected,Correct,Answer\n"
    for h in history:
        csv_content += f'"{h["question"]}",{h["selected"]},{h["correct"]},{h["answer"]}\n'

    filename = f"quiz_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return dict(content=csv_content, filename=filename)


if __name__ == "__main__":
    print("🚀 Starting PrashnAI Quiz App...")
    print(f"📁 Quiz directory: {QUIZ_DIR}")
    print(f"📄 Available files: {len(quiz_files)}")
    print("🌐 Open http://127.0.0.1:8050 in your browser")
    app.run(debug=True, host='127.0.0.1', port=8050)