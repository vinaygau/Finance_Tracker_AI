import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import sqlite3
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import time
import requests

# Initialize database
def init_db():
    retries = 5
    for attempt in range(retries):
        try:
            conn = sqlite3.connect('finance.db', check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute('''DROP TABLE IF EXISTS expenses''')
            c.execute('''DROP TABLE IF EXISTS budgets''')
            c.execute('''DROP TABLE IF EXISTS savings_goals''')
            c.execute('''DROP TABLE IF EXISTS income''')
            c.execute('''DROP TABLE IF EXISTS users''')
            c.execute('''DROP TABLE IF EXISTS investments''')
            c.execute('''DROP TABLE IF EXISTS recurring''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY, username TEXT, password TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS expenses
                        (expense_id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, 
                        category TEXT, subcategory TEXT, date DATE, description TEXT, 
                        payment_method TEXT, FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS budgets
                        (budget_id INTEGER PRIMARY KEY, user_id INTEGER, category TEXT, 
                        subcategory TEXT, limit_amount REAL, period TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                        (goal_id INTEGER PRIMARY KEY, user_id INTEGER, goal_name TEXT, 
                        target_amount REAL, current_amount REAL, target_date DATE, 
                        priority INTEGER, description TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS income
                        (income_id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, 
                        source TEXT, date DATE, description TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS investments
                        (inv_id INTEGER PRIMARY KEY, user_id INTEGER, asset_name TEXT, 
                        amount_invested REAL, current_value REAL, purchase_date DATE,
                        FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS recurring
                        (rec_id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, 
                        amount REAL, category TEXT, frequency TEXT, next_date DATE,
                        FOREIGN KEY(user_id) REFERENCES users(user_id))''')
            
            c.execute("INSERT OR IGNORE INTO users (user_id, username, password) VALUES (?, ?, ?)", (1, 'user1', 'pass1'))
            conn.commit()
            return conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                time.sleep(1)
                continue
            else:
                st.error(f"Database error: {e}")
                raise
    st.error("Failed to initialize database after multiple attempts.")
    return None

# Load CSV into database
def load_csv_to_db(conn, uploaded_file, user_id):
    c = conn.cursor()
    uploaded_df = pd.read_csv(uploaded_file)
    c.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM income WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM savings_goals WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM investments WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM recurring WHERE user_id = ?", (user_id,))
    
    for index, row in uploaded_df.iterrows():
        data_type = row.get('type', '').lower()
        try:
            if data_type == 'expense':
                c.execute("INSERT INTO expenses (user_id, amount, category, date, description, payment_method) VALUES (?, ?, ?, ?, ?, ?)",
                          (user_id, row.get('amount', 0), row.get('category', 'Other'), row.get('date', datetime.now().strftime('%Y-%m-%d')),
                           row.get('description', ''), row.get('payment_method', 'Unknown')))
            elif data_type == 'income':
                c.execute("INSERT INTO income (user_id, amount, source, date, description) VALUES (?, ?, ?, ?, ?)",
                          (user_id, row.get('amount', 0), row.get('source', 'Other'), row.get('date', datetime.now().strftime('%Y-%m-%d')),
                           row.get('description', '')))
            elif data_type == 'savings':
                c.execute("INSERT INTO savings_goals (user_id, goal_name, target_amount, current_amount, target_date, priority) VALUES (?, ?, ?, ?, ?, ?)",
                          (user_id, row.get('goal_name', 'Unnamed Goal'), row.get('target_amount', 0), row.get('current_amount', 0),
                           row.get('target_date', '2025-12-31'), row.get('priority', 1)))
            elif data_type == 'budget':
                c.execute("INSERT INTO budgets (user_id, category, limit_amount, period) VALUES (?, ?, ?, ?)",
                          (user_id, row.get('category', 'Other'), row.get('limit_amount', 0), row.get('period', 'Monthly')))
            elif data_type == 'investment':
                c.execute("INSERT INTO investments (user_id, asset_name, amount_invested, current_value, purchase_date) VALUES (?, ?, ?, ?, ?)",
                          (user_id, row.get('asset_name', 'Unknown'), row.get('amount_invested', 0), row.get('current_value', 0),
                           row.get('purchase_date', datetime.now().strftime('%Y-%m-%d'))))
            elif data_type == 'recurring':
                c.execute("INSERT INTO recurring (user_id, type, amount, category, frequency, next_date) VALUES (?, ?, ?, ?, ?, ?)",
                          (user_id, row.get('rec_type', 'expense'), row.get('amount', 0), row.get('category', 'Other'),
                           row.get('frequency', 'Monthly'), row.get('next_date', datetime.now().strftime('%Y-%m-%d'))))
        except KeyError as e:
            st.warning(f"Skipping row {index}: Missing column {e}")
    conn.commit()
    return uploaded_df

# Initialize database
conn = init_db()
if conn is None:
    st.stop()

# Page config
st.set_page_config(page_title="ProFinance Manager", layout="wide", initial_sidebar_state="expanded")

# Fancy Sidebar
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #00CC96;'>💼 ProFinance</h1>", unsafe_allow_html=True)
    st.markdown("---")
    menu = st.expander("📋 Menu", expanded=True)
    with menu:
        page = st.radio("Navigation", ["🏠 Dashboard", "💸 Expenses", "💵 Income", "📊 Budgets", "🎯 Goals", 
                                       "📈 Analytics", "📑 Reports", "💰 Investments", "🔄 Recurring"], 
                       label_visibility="hidden")  # Hidden label for accessibility
    st.markdown("---")
    st.subheader("📤 Upload Data")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], help="Supported types: expense, income, savings, budget, investment, recurring")
    if uploaded_file:
        uploaded_df = load_csv_to_db(conn, uploaded_file, 1)
        st.success("Data loaded successfully!")
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by xAI</p>", unsafe_allow_html=True)

current_user_id = 1
page = page.split()[1]  # Extract page name from sidebar radio

# Dynamic Categories
DEFAULT_EXPENSE_CATEGORIES = ["Housing", "Food", "Transportation", "Utilities", "Healthcare", "Entertainment", "Education", "Personal", "Debt Payments", "Savings", "Investments", "Gifts", "Other"]
DEFAULT_PAYMENT_METHODS = ["Cash", "Credit Card", "Debit Card", "Bank Transfer", "Digital Wallet", "Check"]
DEFAULT_INCOME_SOURCES = ["Salary", "Freelance", "Investments", "Rental", "Business", "Gifts", "Other"]

def get_dynamic_categories(conn, table, column, user_id, default_list):
    df = pd.read_sql(f"SELECT DISTINCT {column} FROM {table} WHERE user_id = ? AND {column} IS NOT NULL", conn, params=(user_id,))
    categories = df[column].tolist()
    return categories if categories else default_list

EXPENSE_CATEGORIES = get_dynamic_categories(conn, "expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
PAYMENT_METHODS = get_dynamic_categories(conn, "expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
INCOME_SOURCES = get_dynamic_categories(conn, "income", "source", current_user_id, DEFAULT_INCOME_SOURCES)

def get_last_month():
    today = datetime.now()
    first_day = today.replace(day=1)
    last_month = first_day - timedelta(days=1)
    return last_month.strftime("%Y-%m")

# Currency Converter (placeholder)
def convert_currency(amount, from_currency="USD", to_currency="EUR"):
    return amount  # Replace with real API call if needed

# PDF Report
def generate_pdf_report(conn, user_id):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph("ProFinance Report", styles['Title']))
    current_month = datetime.now().strftime("%Y-%m")
    monthly_spending = pd.read_sql("SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(user_id, current_month)).iloc[0,0] or 0
    monthly_income = pd.read_sql("SELECT SUM(amount) as total FROM income WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(user_id, current_month)).iloc[0,0] or 0
    savings = pd.read_sql("SELECT SUM(current_amount) as saved FROM savings_goals WHERE user_id = ?", conn, params=(user_id,)).iloc[0,0] or 0
    profit = monthly_income - monthly_spending
    inv_value = pd.read_sql("SELECT SUM(current_value) as total FROM investments WHERE user_id = ?", conn, params=(user_id,)).iloc[0,0] or 0
    
    summary_data = [
        ["Metric", "Value"],
        ["Monthly Spending", f"${monthly_spending:,.2f}"],
        ["Monthly Income", f"${monthly_income:,.2f}"],
        ["Profit", f"${profit:,.2f}"],
        ["Savings", f"${savings:,.2f}"],
        ["Investment Value", f"${inv_value:,.2f}"]
    ]
    table = Table(summary_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Dashboard
if page == "Dashboard":
    st.title("🏠 Finance Dashboard")
    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    last_month = get_last_month()
    
    cols = st.columns(4)
    with cols[0]:
        monthly_spending = pd.read_sql("SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(current_user_id, current_month)).iloc[0,0] or 0
        last_month_spending = pd.read_sql("SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(current_user_id, last_month)).iloc[0,0] or 0
        change = ((monthly_spending - last_month_spending) / last_month_spending * 100) if last_month_spending else 0
        st.metric("Monthly Spending", f"${monthly_spending:,.2f}", f"{change:.1f}%")
    with cols[1]:
        monthly_income = pd.read_sql("SELECT SUM(amount) as total FROM income WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(current_user_id, current_month)).iloc[0,0] or 0
        last_month_income = pd.read_sql("SELECT SUM(amount) as total FROM income WHERE user_id = ? AND strftime('%Y-%m', date) = ?", conn, params=(current_user_id, last_month)).iloc[0,0] or 0
        income_change = ((monthly_income - last_month_income) / last_month_income * 100) if last_month_income else 0
        st.metric("Monthly Income", f"${monthly_income:,.2f}", f"{income_change:.1f}%")
    with cols[2]:
        profit = monthly_income - monthly_spending
        last_month_profit = last_month_income - last_month_spending
        profit_change = ((profit - last_month_profit) / last_month_profit * 100) if last_month_profit else 0
        st.metric("Monthly Profit", f"${profit:,.2f}", f"{profit_change:.1f}%")
    with cols[3]:
        savings = pd.read_sql("SELECT SUM(current_amount) as saved FROM savings_goals WHERE user_id = ?", conn, params=(current_user_id,)).iloc[0,0] or 0
        target = pd.read_sql("SELECT SUM(target_amount) as target FROM savings_goals WHERE user_id = ?", conn, params=(current_user_id,)).iloc[0,0] or 0
        progress = (savings / target * 100) if target else 0
        st.metric("Savings Progress", f"${savings:,.2f}", f"{progress:.1f}% of ${target:,.2f}")

    st.subheader("Financial Overview")
    time_period = st.selectbox("Time Period", ["Last 3 Months", "Last 6 Months", "Last 12 Months", "Current Year"])
    date_filter = {
        "Last 3 Months": "-3 months",
        "Last 6 Months": "-6 months",
        "Last 12 Months": "-12 months",
        "Current Year": "strftime('%Y', date) = strftime('%Y', 'now')"
    }[time_period]
    
    # Corrected SQL queries
    if time_period == "Current Year":
        spending_data = pd.read_sql("SELECT strftime('%Y-%m', date) as month, SUM(amount) as spending FROM expenses WHERE user_id = ? AND " + date_filter + " GROUP BY month ORDER BY month",
                                    conn, params=(current_user_id,))
        income_data = pd.read_sql("SELECT strftime('%Y-%m', date) as month, SUM(amount) as income FROM income WHERE user_id = ? AND " + date_filter + " GROUP BY month ORDER BY month",
                                  conn, params=(current_user_id,))
    else:
        spending_data = pd.read_sql("SELECT strftime('%Y-%m', date) as month, SUM(amount) as spending FROM expenses WHERE user_id = ? AND date >= date('now', ?) GROUP BY month ORDER BY month",
                                    conn, params=(current_user_id, date_filter))
        income_data = pd.read_sql("SELECT strftime('%Y-%m', date) as month, SUM(amount) as income FROM income WHERE user_id = ? AND date >= date('now', ?) GROUP BY month ORDER BY month",
                                  conn, params=(current_user_id, date_filter))
    
    comparison_data = pd.merge(spending_data, income_data, on='month', how='outer').fillna(0)
    comparison_data['profit'] = comparison_data['income'] - comparison_data['spending']
    fig = px.bar(comparison_data, x='month', y=['income', 'spending', 'profit'], barmode='group', title=f"Financial Flow ({time_period})",
                 labels={'value': 'Amount ($)', 'month': 'Month'}, color_discrete_map={'income': '#00CC96', 'spending': '#EF553B', 'profit': '#636EFA'})
    st.plotly_chart(fig)

# Expenses
elif page == "Expenses":
    st.title("💸 Expense Tracking")
    with st.form("expense_form"):
        amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
        col1, col2 = st.columns(2)
        category = col1.selectbox("Category", EXPENSE_CATEGORIES + ["Add New"])
        if category == "Add New":
            category = col1.text_input("New Category")
        subcategory = col2.text_input("Subcategory (Optional)")
        col1, col2 = st.columns(2)
        date = col1.date_input("Date", datetime.now())
        payment_method = col2.selectbox("Payment Method", PAYMENT_METHODS + ["Add New"])
        if payment_method == "Add New":
            payment_method = col2.text_input("New Payment Method")
        description = st.text_input("Description (Optional)")
        submitted = st.form_submit_button("Add Expense")
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO expenses (user_id, amount, category, subcategory, date, description, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (current_user_id, amount, category, subcategory, str(date), description, payment_method))
            conn.commit()
            st.success("Expense added!")
            EXPENSE_CATEGORIES = get_dynamic_categories(conn, "expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
            PAYMENT_METHODS = get_dynamic_categories(conn, "expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)

    st.subheader("Expense Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    expenses_df = pd.read_sql("SELECT date, category, amount, payment_method, description FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC",
                              conn, params=(current_user_id, str(start_date), str(end_date)))
    total_spent = expenses_df['amount'].sum()
    avg_daily = total_spent / ((end_date - start_date).days + 1) if (end_date - start_date).days > 0 else total_spent
    st.write(f"**Total Spent:** ${total_spent:,.2f} | **Avg Daily:** ${avg_daily:,.2f}")
    st.dataframe(expenses_df)
    csv = expenses_df.to_csv(index=False)
    st.download_button("Download Expenses as CSV", csv, "expenses.csv", "text/csv")
    
    cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
    fig = px.pie(cat_data, values='amount', names='category', title="Expense Distribution")
    st.plotly_chart(fig)

# Income
elif page == "Income":
    st.title("💵 Income Tracking")
    with st.form("income_form"):
        amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
        col1, col2 = st.columns(2)
        source = col1.selectbox("Source", INCOME_SOURCES + ["Add New"])
        if source == "Add New":
            source = col1.text_input("New Source")
        date = col2.date_input("Date", datetime.now())
        description = st.text_input("Description (Optional)")
        submitted = st.form_submit_button("Add Income")
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO income (user_id, amount, source, date, description) VALUES (?, ?, ?, ?, ?)",
                      (current_user_id, amount, source, str(date), description))
            conn.commit()
            st.success("Income added!")
            INCOME_SOURCES = get_dynamic_categories(conn, "income", "source", current_user_id, DEFAULT_INCOME_SOURCES)
    
    st.subheader("Income Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    income_df = pd.read_sql("SELECT date, source, amount, description FROM income WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC",
                            conn, params=(current_user_id, str(start_date), str(end_date)))
    total_income = income_df['amount'].sum()
    avg_daily = total_income / ((end_date - start_date).days + 1) if (end_date - start_date).days > 0 else total_income
    st.write(f"**Total Income:** ${total_income:,.2f} | **Avg Daily:** ${avg_daily:,.2f}")
    st.dataframe(income_df)
    csv = income_df.to_csv(index=False)
    st.download_button("Download Income as CSV", csv, "income.csv", "text/csv")
    
    source_data = income_df.groupby('source')['amount'].sum().reset_index()
    fig = px.bar(source_data, x='source', y='amount', title="Income by Source", labels={'source': 'Income Source', 'amount': 'Amount ($)'})
    st.plotly_chart(fig)

# Budgets
elif page == "Budgets":
    st.title("📊 Budget Management")
    tab1, tab2 = st.tabs(["Set Budgets", "Budget Analysis"])
    with tab1:
        with st.form("budget_form"):
            category = st.selectbox("Category", EXPENSE_CATEGORIES + ["Add New"])
            if category == "Add New":
                category = st.text_input("New Category")
            limit_amount = st.number_input("Monthly Limit ($)", min_value=0.01, step=0.01)
            submitted = st.form_submit_button("Save Budget")
            if submitted:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO budgets (user_id, category, limit_amount, period) VALUES (?, ?, ?, ?)",
                          (current_user_id, category, limit_amount, "Monthly"))
                conn.commit()
                st.success("Budget saved!")
                EXPENSE_CATEGORIES = get_dynamic_categories(conn, "expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
    with tab2:
        current_month = datetime.now().strftime("%Y-%m")
        budget_status = pd.read_sql("""
            SELECT b.category, b.limit_amount, COALESCE(SUM(e.amount), 0) as spent
            FROM budgets b
            LEFT JOIN expenses e ON b.category = e.category AND strftime('%Y-%m', e.date) = ?
            WHERE b.user_id = ?
            GROUP BY b.category, b.limit_amount
        """, conn, params=(current_month, current_user_id))
        budget_status['remaining'] = budget_status['limit_amount'] - budget_status['spent']
        budget_status['progress'] = (budget_status['spent'] / budget_status['limit_amount'] * 100).clip(0, 100)
        st.dataframe(budget_status)
        fig = px.bar(budget_status, x='category', y=['spent', 'limit_amount'], barmode='group', title="Budget vs Actual Spending")
        st.plotly_chart(fig)

# Goals
elif page == "Goals":
    st.title("🎯 Savings Goals")
    with st.form("goal_form"):
        goal_name = st.text_input("Goal Name")
        target_amount = st.number_input("Target Amount ($)", min_value=0.01)
        current_amount = st.number_input("Current Amount ($)", min_value=0.0)
        target_date = st.date_input("Target Date")
        priority = st.slider("Priority", 1, 5, 3)
        description = st.text_area("Description (Optional)")
        submitted = st.form_submit_button("Add Goal")
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO savings_goals (user_id, goal_name, target_amount, current_amount, target_date, priority, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (current_user_id, goal_name, target_amount, current_amount, str(target_date), priority, description))
            conn.commit()
            st.success("Goal added!")
    
    st.subheader("Goal Progress")
    goals = pd.read_sql("SELECT goal_name, target_amount, current_amount, target_date FROM savings_goals WHERE user_id = ?", conn, params=(current_user_id,))
    goals['progress'] = (goals['current_amount'] / goals['target_amount'] * 100).clip(0, 100)
    for _, row in goals.iterrows():
        st.write(f"**{row['goal_name']}** - Target: ${row['target_amount']:,.2f} by {row['target_date']}")
        st.progress(row['progress']/100, f"Progress: ${row['current_amount']:,.2f} ({row['progress']:.1f}%)")
    fig = px.bar(goals, x='goal_name', y=['current_amount', 'target_amount'], barmode='group', title="Savings Goals Progress")
    st.plotly_chart(fig)

# Investments
elif page == "Investments":
    st.title("💰 Investment Tracking")
    with st.form("investment_form"):
        asset_name = st.text_input("Asset Name (e.g., Stock, Crypto)")
        amount_invested = st.number_input("Amount Invested ($)", min_value=0.01)
        current_value = st.number_input("Current Value ($)", min_value=0.0)
        purchase_date = st.date_input("Purchase Date", datetime.now())
        submitted = st.form_submit_button("Add Investment")
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO investments (user_id, asset_name, amount_invested, current_value, purchase_date) VALUES (?, ?, ?, ?, ?)",
                      (current_user_id, asset_name, amount_invested, current_value, str(purchase_date)))
            conn.commit()
            st.success("Investment added!")
    
    st.subheader("Investment Portfolio")
    inv_df = pd.read_sql("SELECT asset_name, amount_invested, current_value, purchase_date FROM investments WHERE user_id = ?", conn, params=(current_user_id,))
    total_value = inv_df['current_value'].sum()
    total_invested = inv_df['amount_invested'].sum()
    roi = ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0
    st.write(f"**Total Invested:** ${total_invested:,.2f} | **Current Value:** ${total_value:,.2f} | **ROI:** {roi:.1f}%")
    st.dataframe(inv_df)
    fig = px.bar(inv_df, x='asset_name', y=['amount_invested', 'current_value'], barmode='group', title="Investment Performance")
    st.plotly_chart(fig)

# Recurring Transactions
elif page == "Recurring":
    st.title("🔄 Recurring Transactions")
    with st.form("recurring_form"):
        rec_type = st.selectbox("Type", ["Expense", "Income"])
        amount = st.number_input("Amount ($)", min_value=0.01)
        category = st.selectbox("Category", EXPENSE_CATEGORIES + INCOME_SOURCES + ["Add New"])
        if category == "Add New":
            category = st.text_input("New Category")
        frequency = st.selectbox("Frequency", ["Daily", "Weekly", "Monthly", "Yearly"])
        next_date = st.date_input("Next Occurrence", datetime.now())
        submitted = st.form_submit_button("Add Recurring")
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO recurring (user_id, type, amount, category, frequency, next_date) VALUES (?, ?, ?, ?, ?, ?)",
                      (current_user_id, rec_type, amount, category, frequency, str(next_date)))
            conn.commit()
            st.success("Recurring transaction added!")
    
    st.subheader("Recurring List")
    rec_df = pd.read_sql("SELECT type, amount, category, frequency, next_date FROM recurring WHERE user_id = ?", conn, params=(current_user_id,))
    st.dataframe(rec_df)

# Analytics
elif page == "Analytics":
    st.title("📈 Financial Analytics")
    st.subheader("Income vs Expenses Trend")
    time_period = st.selectbox("Time Period", ["Last 3 Months", "Last 6 Months", "Last 12 Months"])
    date_filter = {"Last 3 Months": '-3 months', "Last 6 Months": '-6 months', "Last 12 Months": '-12 months'}[time_period]
    monthly_data = pd.read_sql("""
        SELECT strftime('%Y-%m', date) as month,
               SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM (SELECT date, -amount as amount FROM expenses WHERE user_id = ?
              UNION ALL
              SELECT date, amount FROM income WHERE user_id = ?)
        WHERE date >= date('now', ?)
        GROUP BY month
        ORDER BY month
    """, conn, params=(current_user_id, current_user_id, date_filter))
    monthly_data['profit'] = monthly_data['income'] - (-monthly_data['expenses'])  # Corrected profit calculation
    fig = px.line(monthly_data, x='month', y=['income', 'expenses', 'profit'], title=f"Financial Trends ({time_period})",
                  labels={'value': 'Amount ($)', 'month': 'Month'}, color_discrete_map={'income': '#00CC96', 'expenses': '#EF553B', 'profit': '#636EFA'})
    st.plotly_chart(fig)
    
    st.subheader("Financial Health Indicators")
    profit_rate = (monthly_data['profit'].mean() / monthly_data['income'].mean() * 100) if monthly_data['income'].mean() else 0
    st.metric("Average Profit Rate", f"{profit_rate:.1f}%")
    expense_ratio = (-monthly_data['expenses'].mean() / monthly_data['income'].mean() * 100) if monthly_data['income'].mean() else 0
    st.metric("Expense-to-Income Ratio", f"{expense_ratio:.1f}%")
    
    st.subheader("Tax Estimation (Premium Feature)")
    st.info("Unlock tax insights with ProFinance Premium! Estimated tax: ~15-30% of profit (simplified).")

# Reports
elif page == "Reports":
    st.title("📑 Financial Reports")
    with st.form("report_form"):
        report_period = st.selectbox("Report Period", ["Current Month", "Last 3 Months", "Last 6 Months"])
        currency = st.selectbox("Currency", ["USD", "EUR", "GBP"])
        submitted = st.form_submit_button("Generate PDF Report")
        if submitted:
            pdf_buffer = generate_pdf_report(conn, current_user_id)
            if currency != "USD":
                st.warning("Currency conversion in PDF is illustrative. Full support in Premium.")
            st.download_button("Download PDF Report", pdf_buffer, "financial_report.pdf", "application/pdf")
            st.success("Report generated successfully!")
    
    st.subheader("Profit Maximization Tips")
    profit = monthly_income - monthly_spending
    if profit > 0:
        st.success(f"Profit: ${profit:,.2f}. Consider investing in low-risk ETFs or bonds.")
    else:
        st.warning(f"Loss: ${-profit:,.2f}. Reduce discretionary spending to boost profit.")

conn.close()