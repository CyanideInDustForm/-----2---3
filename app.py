from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import psycopg2

app = Flask(__name__)
app.secret_key = '12345678'


# PostgreSQL connection params
pg_config = {
    "host": "localhost",
    "port": "5432",
    "dbname": "3d_packages_db",
    "user": "postgres",
    "password": "12345678"
}

# SQLite DB path
sqlite_path = "3d_packages_base.db"

# Global state to switch databases
current_db = {"type": "sqlite"}

def get_sqlite_connection():
    return sqlite3.connect(sqlite_path)

def get_pg_connection():
    return psycopg2.connect(**pg_config)

def get_connection():
    return get_pg_connection() if current_db["type"] == "postgres" else get_sqlite_connection()

@app.route("/")
def index():
    return redirect(url_for("stats"))

@app.route("/switch_db")
def switch_db():
    current_db["type"] = "postgres" if current_db["type"] == "sqlite" else "sqlite"
    return redirect(url_for("stats"))

@app.route("/stats")
def stats():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';" if current_db["type"] == "sqlite" else "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = cursor.fetchall()
        stats = {}
        for (table,) in tables:
            try:
                # Экранируем имя таблицы
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                result = cursor.fetchone()
                stats[table] = result[0] if result else 0
            except Exception as e:
                print(f"Ошибка при обработке таблицы {table}: {e}")
                stats[table] = "Ошибка"
    finally:
        cursor.close()
        conn.close()

    return render_template("stats.html", db_type=current_db["type"], stats=stats)

@app.route("/search", methods=["GET", "POST"])
def search():
    result = []
    columns = [] 
    selected_table = request.form.get("table") if request.method == "POST" else None
    filters = {k: v for k, v in request.form.items() if k != "table" and k != "submit" and v}

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';" if current_db["type"] == "sqlite" else "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = [t[0] for t in cursor.fetchall()]

        if selected_table:
            if current_db["type"] == "sqlite":
                cursor.execute(f"PRAGMA table_info(`{selected_table}`);")
                columns = [col[1] for col in cursor.fetchall()]
            else:
                cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{selected_table}';")
                columns = [col[0] for col in cursor.fetchall()]

            if filters:
                if current_db["type"] == "postgres":
                    where_clause = " AND ".join([f'"{k}"::text LIKE %s' for k in filters.keys()])
                    params = [f'%{v}%' for v in filters.values()]
                else:
                    where_clause = " AND ".join([f"`{k}` LIKE ?" for k in filters.keys()])
                    params = [f'%{v}%' for v in filters.values()]
            else:
                where_clause = ""
                params = []

            if current_db["type"] == "postgres":
                query = f'SELECT * FROM "{selected_table}"' + (f" WHERE {where_clause}" if where_clause else "")
                cursor.execute(query, params)
            else:
                query = f"SELECT * FROM `{selected_table}`" + (f" WHERE {where_clause}" if where_clause else "")
                cursor.execute(query, params)

            result = cursor.fetchall()

            # Insert if form is filled
            if "submit" in request.form and request.form["submit"] == "Добавить":
                values = [request.form.get(col, "") for col in columns]
                placeholders = ','.join(['%s' if current_db["type"] == "postgres" else '?'] * len(values))
                if current_db["type"] == "postgres":
                    cols = ','.join([f'"{col}"' for col in columns])
                    insert_query = f'INSERT INTO "{selected_table}" ({cols}) VALUES ({placeholders})'
                else:
                    cols = ','.join([f'`{col}`' for col in columns])
                    insert_query = f"INSERT INTO `{selected_table}` ({cols}) VALUES ({placeholders})"
                try:
                    cursor.execute(insert_query, values)
                    conn.commit()
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    flash("Пожалуйста, введите уникальное значение для поля-счетчика записей", "error")
                    result = []
                    columns = columns
                except (psycopg2.errors.CheckViolation, sqlite3.IntegrityError) as e:
                    conn.rollback()
                    flash("Ошибка: введены неверные данные, пожалуйста, введите их заново.", "error")
                    result = []
                    columns = columns

    finally:
        cursor.close()
        conn.close()

    return render_template("search.html", tables=tables, selected_table=selected_table, columns=columns, result=result)

@app.route("/reference")
def reference():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if current_db["type"] == "postgres":
            cursor.execute('SELECT * FROM "Основные сведения"')
        else:
            cursor.execute("SELECT * FROM `Основные сведения`")
        products = cursor.fetchall()
        cursor.execute("PRAGMA table_info(`Основные сведения`);" if current_db["type"] == "sqlite" else "SELECT column_name FROM information_schema.columns WHERE table_name = 'Основные сведения';")
        columns = [col[1] if current_db["type"] == "sqlite" else col[0] for col in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

    return render_template("reference.html", products=products, columns=columns)

if __name__ == "__main__":
    app.run(debug=True)
