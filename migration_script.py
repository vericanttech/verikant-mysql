import json
from datetime import datetime
from app.extensions import db
from app.models import Note  # Import your Note model
from app import create_app


def migrate_notes_from_json(json_file_path, shop_id=1, user_id=1):  # shop_id and user_id default to 1
    """Migrates notes from a JSON file."""

    try:
        with open(json_file_path, 'r', encoding='utf-8') as file:
            notes_data = json.load(file)

        app = create_app()
        with app.app_context():
            successful = 0
            failed = 0

            for _, note_data in notes_data.items():  # Iterate through the values (no need for keys)
                try:
                    balde_data = note_data.get("admin")  # get balde data
                    if balde_data:  # check if balde data exists
                        date_str = balde_data.get("date")
                        note_content = balde_data.get("note")

                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")  # Parse date (only date part)
                        date = date_obj.strftime("%Y-%m-%d")

                        new_note = Note(
                            shop_id=shop_id,
                            title=f"Note for {date}",  # You can customize the title
                            content=note_content,
                            user_id=user_id,
                        )

                        db.session.add(new_note)
                        successful += 1

                    else:
                        print("admin key not found")
                        continue

                except ValueError as ve:
                    failed += 1
                    print(f"Error processing note: Invalid data format: {ve}")
                    db.session.rollback()
                    continue
                except Exception as e:
                    failed += 1
                    print(f"Error inserting note: {e}")
                    db.session.rollback()
                    continue

            try:
                db.session.commit()
                print("\nNote Migration Summary:")
                print(f"- Successful migrations: {successful}")
                print(f"- Failed migrations: {failed}")
            except Exception as e:
                db.session.rollback()
                print(f"\nFailed to commit changes to database: {str(e)}")
                return False

        return True

    except FileNotFoundError:
        print(f"Error: Could not find file at {json_file_path}")
        return False
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in file {json_file_path}")
        return False
    except Exception as e:
        print(f"Unexpected error during migration: {str(e)}")
        return False


#notes_file_path = r"C:\Users\casper\Desktop\sobafi2025\sobafi_notes.json"
#migrate_notes_from_json(notes_file_path)  # shop_id and user_id will be 1 by default.
