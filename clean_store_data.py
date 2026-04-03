import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import (
    Product, Client, SalesBill, SalesDetail, Category, Expense, Loan, Supplier, SupplierBill, Check, BoutiqueTransaction, Note, StockMovement, PaymentTransaction, EmployeeSalary, EmployeeLoan, EmployeeLoanPayment
)

def main():
    # Accept shop_id as a command-line argument
    shop_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    app = create_app()
    with app.app_context():
        session = db.session
        # Delete in order of dependencies (children first)
        models = [
            SalesDetail,
            SalesBill,
            Product,
            Client,
            Category,
            Expense,
            Loan,
            SupplierBill,
            Supplier,
            Check,
            BoutiqueTransaction,
            Note,
            StockMovement,
            PaymentTransaction,
            EmployeeSalary,
            EmployeeLoanPayment,
            EmployeeLoan,
        ]
        for model in models:
            if model == SalesDetail:
                deleted = session.query(SalesDetail).filter(
                    SalesDetail.bill_id.in_(
                        session.query(SalesBill.id).filter_by(shop_id=shop_id)
                    )
                ).delete(synchronize_session=False)
            else:
                deleted = session.query(model).filter_by(shop_id=shop_id).delete(synchronize_session=False)
            print(f"Deleted {deleted} from {model.__tablename__}")
        session.commit()
        print(f"All data for shop_id={shop_id} deleted.")

if __name__ == '__main__':
    main() 