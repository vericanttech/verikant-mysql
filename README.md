# POS-Master

A comprehensive Point of Sale and Business Management System built with Flask.

## Features

- Point of Sale System
- Inventory Management
- Sales Tracking
- Expense Management
- Financial Reports
- User Authentication
- Multi-database Support

## Installation

1. Clone the repository (default folder name matches the GitHub repo):
   ```bash
   git clone https://github.com/vericanttech/verikant-mysql.git
   cd verikant-mysql
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   **Optional (Node, for Tailwind / refreshing Lucide):** `npm install` copies `lucide.min.js` from the `lucide` package into `app/static/js/lib/` (also run `npm run copy-lucide` after upgrading `lucide` in `package.json`). The built file is committed so the app works without Node on the server.

4. Configure the database:

   - **Production and normal setups:** set `SQLALCHEMY_DATABASE_URI` or `DATABASE_URL` in `.env` (copy from `.env.example`). The app is used with **MySQL** in practice (see `docs/MYSQL_AND_PYTHONANYWHERE.md`).
   - **MySQL (e.g. PythonAnywhere):** use a `mysql+pymysql://...` URL. Database names like `vericant$shop` must use `$` encoded as `%24` in the URL. Dependencies already include `PyMySQL`.
   - **Optional local fallback:** if neither variable is set, the app falls back to **SQLite** at `instance/shop.db` (handy for a quick clone with no DB server; not what we use in production).
   - **SSH tunnel from your PC (if direct MySQL is blocked):** open a tunnel, then use `127.0.0.1` and the local port in your URI. Example:
     ```bash
     ssh -L 3306:vericant.mysql.pythonanywhere-services.com:3306 YOUR_PA_USER@ssh.pythonanywhere.com
     ```
     See [PythonAnywhere: MySQL from outside](https://help.pythonanywhere.com/pages/AccessingMySQLFromOutsidePythonAnywhere).

5. Initialize the database:
   ```bash
   flask db upgrade
   ```

6. Run the application:
   ```bash
   python run.py
   ```

## Google Cloud Run

This repo includes a **`Dockerfile`** and **`.dockerignore`** so you can run the same Flask app on **Cloud Run** (cheaper / scale-to-zero friendly vs many PaaS plans).

- Full steps, env vars, and database notes: **[docs/CLOUD_RUN.md](docs/CLOUD_RUN.md)**

## License

This project is licensed under the MIT License - see the LICENSE file for details.
