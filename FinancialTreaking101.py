import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
import time
import os
import numpy as np
import yfinance as yf
from fpdf import FPDF
from scipy.optimize import minimize
from supabase import create_client, Client

# Set page config as the FIRST Streamlit command
st.set_page_config(
    page_title="ProFinance Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Supabase Configuration
SUPABASE_URL = "https://hugjvlpvxqvnkuzfyacw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1Z2p2bHB2eHF2bmt1emZ5YWN3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ0Nzg4NDIsImV4cCI6MjA2MDA1NDg0Mn0.BDe2Wrr74P-pkR0XF6Sfgheq6k4Z0LvidHV-7JiDC30"

# Initialize Supabase client
@st.cache_resource(ttl=3600)
def init_supabase():
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        st.success("Connected to Supabase successfully!")
        return supabase
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

# Initialize Supabase connection
supabase = init_supabase()
if supabase is None:
    st.error("Application cannot run without database connection.")
    st.stop()

# Create tables if they don't exist (Supabase handles this through the dashboard)
def create_tables_if_needed():
    try:
        # For Supabase, tables should be created through the dashboard
        # This function is just a placeholder in case you want to check table existence
        pass
    except Exception as e:
        st.error(f"Error checking tables: {e}")

# Create tables on startup
create_tables_if_needed()

# Page configuration
st.set_page_config(
    page_title="ProFinance Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
DEFAULT_EXPENSE_CATEGORIES = ["Housing", "Food", "Transportation", "Utilities", "Healthcare", 
                            "Entertainment", "Education", "Personal", "Debt Payments", 
                            "Savings", "Investments", "Gifts", "Other"]
DEFAULT_PAYMENT_METHODS = ["Cash", "Credit Card", "Debit Card", "Bank Transfer", "Digital Wallet", "Check"]
DEFAULT_INCOME_SOURCES = ["Salary", "Freelance", "Investments", "Rental", "Business", "Gifts", "Other"]
RISK_TOLERANCE_OPTIONS = ["Low", "Medium", "High"]
ASSET_TYPES = ["Stock", "Bond", "ETF", "Mutual Fund", "Crypto", "Real Estate", "Other"]
FREQUENCY_OPTIONS = ["Daily", "Weekly", "Biweekly", "Monthly", "Quarterly", "Yearly"]
PERIOD_OPTIONS = ["Daily", "Weekly", "Monthly", "Yearly"]

# Helper functions
def get_dynamic_categories(table, column, user_id, default_list):
    try:
        response = supabase.table(table).select(column).eq('user_id', user_id).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            categories = df[column].dropna().unique().tolist()
            return list(set(categories + default_list))
        return default_list
    except Exception as e:
        st.error(f"Error fetching categories: {e}")
        return default_list

def get_last_month():
    today = datetime.now()
    first_day = today.replace(day=1)
    last_month = first_day - timedelta(days=1)
    return last_month.strftime("%Y-%m")

# Financial analysis functions
def calculate_financial_ratios(user_id):
    try:
        current_month = datetime.now().strftime("%Y-%m")
        
        # Get monthly income
        income_response = supabase.rpc('get_monthly_income', {
            'user_id': user_id,
            'month': current_month
        }).execute()
        monthly_income = income_response.data[0]['total'] if income_response.data else 0
        
        # Get monthly expenses
        expenses_response = supabase.rpc('get_monthly_expenses', {
            'user_id': user_id,
            'month': current_month
        }).execute()
        monthly_expenses = expenses_response.data[0]['total'] if expenses_response.data else 0
        
        # Get investment value
        investments_response = supabase.table('investments').select('current_value').eq('user_id', user_id).execute()
        total_assets = sum(item['current_value'] for item in investments_response.data) if investments_response.data else 0
        
        # Calculate ratios
        savings_rate = ((monthly_income - monthly_expenses) / monthly_income * 100) if monthly_income > 0 else 0
        expense_ratio = (monthly_expenses / monthly_income * 100) if monthly_income > 0 else 0
        net_worth = total_assets
        
        # Store ratios in database
        supabase.table('financial_ratios').insert([
            {'user_id': user_id, 'date': datetime.now().date().isoformat(), 'ratio_name': 'Savings Rate', 'ratio_value': savings_rate},
            {'user_id': user_id, 'date': datetime.now().date().isoformat(), 'ratio_name': 'Expense Ratio', 'ratio_value': expense_ratio},
            {'user_id': user_id, 'date': datetime.now().date().isoformat(), 'ratio_name': 'Net Worth', 'ratio_value': net_worth}
        ]).execute()
        
        return {
            'savings_rate': savings_rate,
            'expense_ratio': expense_ratio,
            'net_worth': net_worth
        }
        
    except Exception as e:
        st.error(f"Error calculating financial ratios: {e}")
        return None

def optimize_budget(user_id):
    try:
        response = supabase.rpc('get_expenses_last_3_months', {'user_id': user_id}).execute()
        expenses = pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        if expenses.empty:
            return None
        
        # Simple optimization: reduce spending by 10% in each category
        recommendations = []
        for _, row in expenses.iterrows():
            recommended = row['total'] * 0.9
            savings = row['total'] - recommended
            recommendations.append({
                'category': row['category'],
                'recommended_amount': recommended,
                'savings_potential': savings
            })
        
        # Store results
        data = [{
            'user_id': user_id,
            'date': datetime.now().date().isoformat(),
            'category': rec['category'],
            'recommended_amount': rec['recommended_amount'],
            'savings_potential': rec['savings_potential']
        } for rec in recommendations]
        
        supabase.table('optimization_results').insert(data).execute()
        
        return recommendations
    
    except Exception as e:
        st.error(f"Error optimizing budget: {e}")
        return None

# Get dynamic categories
current_user_id = 1  # Default user
EXPENSE_CATEGORIES = get_dynamic_categories("expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
PAYMENT_METHODS = get_dynamic_categories("expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
INCOME_SOURCES = get_dynamic_categories("income", "source", current_user_id, DEFAULT_INCOME_SOURCES)

# Sidebar navigation
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #00CC96;'>💼 ProFinance</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    menu_options = [
        "🏠 Dashboard",
        "💸 Expenses",
        "💵 Income",
        "📊 Budgets",
        "🎯 Goals",
        "📈 Analytics",
        "📑 Reports",
        "💰 Investments",
        "🔄 Recurring",
        "🧮 Financial Workbench"
    ]
    selected_page = st.radio("Navigation", menu_options, label_visibility="hidden")
    
    st.markdown("---")
    st.subheader("Data Import")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success("Data uploaded successfully!")
            st.write(df.head())
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: grey;'>Made with ❤️ by xAI</p>", unsafe_allow_html=True)

# Get current page
current_page = selected_page.split()[1] if selected_page != "🧮 Financial Workbench" else "Financial Workbench"

# Main content area
if current_page == "Dashboard":
    st.title("🏠 Finance Dashboard")
    
    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    last_month = get_last_month()
    
    cols = st.columns(4)
    with cols[0]:
        try:
            monthly_spending_response = supabase.rpc('get_monthly_expenses', {
                'user_id': current_user_id,
                'month': current_month
            }).execute()
            monthly_spending = monthly_spending_response.data[0]['total'] if monthly_spending_response.data else 0
            
            last_month_spending_response = supabase.rpc('get_monthly_expenses', {
                'user_id': current_user_id,
                'month': last_month
            }).execute()
            last_month_spending = last_month_spending_response.data[0]['total'] if last_month_spending_response.data else 0
            
            change = ((monthly_spending - last_month_spending) / last_month_spending * 100) if last_month_spending else 0
            st.metric("Monthly Spending", f"${monthly_spending:,.2f}", f"{change:.1f}%")
        except Exception as e:
            st.error(f"Error loading spending data: {e}")
    
    with cols[1]:
        try:
            monthly_income_response = supabase.rpc('get_monthly_income', {
                'user_id': current_user_id,
                'month': current_month
            }).execute()
            monthly_income = monthly_income_response.data[0]['total'] if monthly_income_response.data else 0
            
            last_month_income_response = supabase.rpc('get_monthly_income', {
                'user_id': current_user_id,
                'month': last_month
            }).execute()
            last_month_income = last_month_income_response.data[0]['total'] if last_month_income_response.data else 0
            
            income_change = ((monthly_income - last_month_income) / last_month_income * 100) if last_month_income else 0
            st.metric("Monthly Income", f"${monthly_income:,.2f}", f"{income_change:.1f}%")
        except Exception as e:
            st.error(f"Error loading income data: {e}")
    
    with cols[2]:
        try:
            profit = monthly_income - monthly_spending
            last_month_profit = last_month_income - last_month_spending
            profit_change = ((profit - last_month_profit) / last_month_profit * 100) if last_month_profit else 0
            st.metric("Monthly Profit", f"${profit:,.2f}", f"{profit_change:.1f}%")
        except:
            st.metric("Monthly Profit", "$0.00", "0.0%")
    
    with cols[3]:
        try:
            savings_response = supabase.rpc('get_savings_progress', {'user_id': current_user_id}).execute()
            if savings_response.data:
                savings = savings_response.data[0]['saved']
                target = savings_response.data[0]['target']
                progress = (savings / target * 100) if target else 0
                st.metric("Savings Progress", f"${savings:,.2f}", f"{progress:.1f}% of ${target:,.2f}")
            else:
                st.metric("Savings Progress", "$0.00", "0.0% of $0.00")
        except Exception as e:
            st.error(f"Error loading savings data: {e}")
    
    st.subheader("Financial Health Indicators")
    try:
        ratios = calculate_financial_ratios(current_user_id)
        if ratios:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Savings Rate", f"{ratios['savings_rate']:.1f}%")
            with col2:
                st.metric("Expense Ratio", f"{ratios['expense_ratio']:.1f}%")
            with col3:
                st.metric("Net Worth", f"${ratios['net_worth']:,.2f}")
    except:
        st.warning("Could not calculate financial ratios")
    
    st.subheader("Financial Trends")
    time_period = st.selectbox("Time Period", ["Last 3 Months", "Last 6 Months", "Last 12 Months", "Current Year"])
    
    try:
        date_condition = {
            "Last 3 Months": "3 MONTH",
            "Last 6 Months": "6 MONTH",
            "Last 12 Months": "12 MONTH",
            "Current Year": "YEAR"
        }[time_period]
        
        spending_response = supabase.rpc('get_spending_trends', {
            'user_id': current_user_id,
            'period': date_condition
        }).execute()
        spending_data = pd.DataFrame(spending_response.data) if spending_response.data else pd.DataFrame()
        
        income_response = supabase.rpc('get_income_trends', {
            'user_id': current_user_id,
            'period': date_condition
        }).execute()
        income_data = pd.DataFrame(income_response.data) if income_response.data else pd.DataFrame()
        
        if not spending_data.empty and not income_data.empty:
            comparison_data = pd.merge(spending_data, income_data, on='month', how='outer').fillna(0)
            comparison_data['profit'] = comparison_data['income'] - comparison_data['spending']
            
            fig = px.bar(
                comparison_data, 
                x='month', 
                y=['income', 'spending', 'profit'], 
                barmode='group',
                title=f"Financial Flow ({time_period})",
                labels={'value': 'Amount ($)', 'month': 'Month'},
                color_discrete_map={
                    'income': '#00CC96', 
                    'spending': '#EF553B', 
                    'profit': '#636EFA'
                }
            )
            st.plotly_chart(fig)
        else:
            st.info("No financial data available")
    
    except Exception as e:
        st.error(f"Error loading financial trends: {e}")

elif current_page == "Expenses":
    st.title("💸 Expense Tracking")
    
    with st.expander("➕ Add New Expense", expanded=True):
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
            
            fixed = st.checkbox("Fixed Expense")
            description = st.text_input("Description (Optional)")
            
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                try:
                    data = {
                        'user_id': current_user_id,
                        'amount': amount,
                        'category': category,
                        'subcategory': subcategory if subcategory else None,
                        'date': date.strftime('%Y-%m-%d'),
                        'description': description if description else None,
                        'payment_method': payment_method,
                        'fixed': fixed
                    }
                    supabase.table('expenses').insert(data).execute()
                    st.success("Expense added successfully!")
                    # Refresh categories
                    EXPENSE_CATEGORIES = get_dynamic_categories("expenses", "category", current_user_id, DEFAULT_EXPENSE_CATEGORIES)
                    PAYMENT_METHODS = get_dynamic_categories("expenses", "payment_method", current_user_id, DEFAULT_PAYMENT_METHODS)
                except Exception as e:
                    st.error(f"Error adding expense: {e}")
    
    st.subheader("Expense Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    try:
        response = supabase.table('expenses').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
        expenses_df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        if not expenses_df.empty:
            total_spent = expenses_df['amount'].sum()
            fixed_expenses = expenses_df[expenses_df['fixed']]['amount'].sum()
            variable_expenses = total_spent - fixed_expenses
            avg_daily = total_spent / ((end_date - start_date).days + 1)
            
            st.write(f"""
                **Total Spent:** ${total_spent:,.2f} | 
                **Fixed:** ${fixed_expenses:,.2f} | 
                **Variable:** ${variable_expenses:,.2f} | 
                **Avg Daily:** ${avg_daily:,.2f}
            """)
            
            st.dataframe(expenses_df)
            
            tab1, tab2, tab3 = st.tabs(["By Category", "By Payment Method", "Fixed vs Variable"])
            
            with tab1:
                cat_data = expenses_df.groupby('category')['amount'].sum().reset_index()
                fig = px.pie(cat_data, values='amount', names='category', title="Expense Distribution by Category")
                st.plotly_chart(fig)
            
            with tab2:
                pm_data = expenses_df.groupby('payment_method')['amount'].sum().reset_index()
                fig = px.bar(pm_data, x='payment_method', y='amount', title="Expenses by Payment Method")
                st.plotly_chart(fig)
            
            with tab3:
                fv_data = expenses_df.groupby('fixed')['amount'].sum().reset_index()
                fv_data['type'] = fv_data['fixed'].apply(lambda x: 'Fixed' if x else 'Variable')
                fig = px.pie(fv_data, values='amount', names='type', title="Fixed vs Variable Expenses")
                st.plotly_chart(fig)
        else:
            st.info("No expenses found for the selected period")
    
    except Exception as e:
        st.error(f"Error loading expenses: {e}")

# Continue with other pages (Income, Budgets, Goals, etc.) following the same pattern...

elif current_page == "Income":
    st.title("💵 Income Tracking")
    
    with st.expander("➕ Add New Income", expanded=True):
        with st.form("income_form"):
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            
            col1, col2 = st.columns(2)
            source = col1.selectbox("Source", INCOME_SOURCES + ["Add New"])
            if source == "Add New":
                source = col1.text_input("New Source")
            
            date = col2.date_input("Date", datetime.now())
            
            fixed = st.checkbox("Fixed Income")
            description = st.text_input("Description (Optional)")
            
            submitted = st.form_submit_button("Add Income")
            if submitted:
                try:
                    data = {
                        'user_id': current_user_id,
                        'amount': amount,
                        'source': source,
                        'date': date.strftime('%Y-%m-%d'),
                        'description': description if description else None,
                        'fixed': fixed
                    }
                    supabase.table('income').insert(data).execute()
                    st.success("Income added successfully!")
                    INCOME_SOURCES = get_dynamic_categories("income", "source", current_user_id, DEFAULT_INCOME_SOURCES)
                except Exception as e:
                    st.error(f"Error adding income: {e}")
    
    st.subheader("Income Analysis")
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = col2.date_input("End Date", datetime.now())
    
    try:
        response = supabase.table('income').select('*').eq('user_id', current_user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
        income_df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        if not income_df.empty:
            total_income = income_df['amount'].sum()
            fixed_income = income_df[income_df['fixed']]['amount'].sum()
            variable_income = total_income - fixed_income
            avg_daily = total_income / ((end_date - start_date).days + 1)
            
            st.write(f"""
                **Total Income:** ${total_income:,.2f} | 
                **Fixed:** ${fixed_income:,.2f} | 
                **Variable:** ${variable_income:,.2f} | 
                **Avg Daily:** ${avg_daily:,.2f}
            """)
            
            st.dataframe(income_df)
            
            tab1, tab2 = st.tabs(["By Source", "Fixed vs Variable"])
            
            with tab1:
                source_data = income_df.groupby('source')['amount'].sum().reset_index()
                fig = px.bar(source_data, x='source', y='amount', title="Income by Source")
                st.plotly_chart(fig)
            
            with tab2:
                fv_data = income_df.groupby('fixed')['amount'].sum().reset_index()
                fv_data['type'] = fv_data['fixed'].apply(lambda x: 'Fixed' if x else 'Variable')
                fig = px.pie(fv_data, values='amount', names='type', title="Fixed vs Variable Income")
                st.plotly_chart(fig)
        else:
            st.info("No income found for the selected period")
    
    except Exception as e:
        st.error(f"Error loading income: {e}")

# Continue with other pages following the same pattern...

elif current_page == "Financial Workbench":
    st.title("🧮 Financial Workbench")
    
    st.subheader("Portfolio Optimization")
    try:
        response = supabase.table('investments').select('asset_name,current_value,expected_return,risk_level').eq('user_id', current_user_id).execute()
        investments = pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        if not investments.empty:
            # Simple optimization example
            def objective(weights, returns):
                return -np.sum(returns * weights)
            
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            bounds = tuple((0, 1) for _ in range(len(investments)))
            initial_guess = [1./len(investments)] * len(investments)
            
            result = minimize(
                objective,
                initial_guess,
                args=(investments['expected_return'],),
                method='SLSQP',
                bounds=bounds,
                constraints=constraints
            )
            
            if result.success:
                optimized_weights = result.x
                allocation = pd.DataFrame({
                    'Asset': investments['asset_name'],
                    'Optimal Weight': optimized_weights
                })
                st.write("Optimized Portfolio Allocation")
                st.dataframe(allocation)
                
                fig = px.pie(
                    allocation, 
                    values='Optimal Weight', 
                    names='Asset', 
                    title="Optimized Portfolio Allocation"
                )
                st.plotly_chart(fig)
            else:
                st.warning("Optimization failed")
        else:
            st.info("No investments available for optimization")
    
    except Exception as e:
        st.error(f"Error optimizing portfolio: {e}")
