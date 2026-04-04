"""One-off: ensure employee_* tables exist via db.create_all(). Prefer Alembic for production schema."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app, db
from app.models import EmployeeSalary, EmployeeLoan, EmployeeLoanPayment


def create_employee_tables():
    app = create_app()
    with app.app_context():
        try:
            # Create the new tables
            db.create_all()
            print("Employee tables created successfully!")
            print("Tables created:")
            print("- employee_salaries")
            print("- employee_loans")
            print("- employee_loan_payments")
        except Exception as e:
            print(f"Error creating employee tables: {str(e)}")


if __name__ == "__main__":
    create_employee_tables()
