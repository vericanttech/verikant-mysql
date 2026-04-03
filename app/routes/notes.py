from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import Note
from sqlalchemy import desc

notes = Blueprint('notes', __name__)


@notes.route('/notes', methods=['GET', 'POST'])
@login_required
def note_list():
    if request.method == 'POST':
        if 'add_note' in request.form:
            content = request.form.get('note')
            title = content[:50] + ('...' if len(content) > 50 else '')

            note = Note(
                title=title,
                content=content,
                user_id=current_user.id,
                shop_id=current_user.current_shop_id
            )
            db.session.add(note)
            db.session.commit()
            flash('Note added successfully!', 'success')

        elif 'edit_note' in request.form:
            note = Note.query.get_or_404(request.form.get('note_id'))
            if note.user_id == current_user.id and note.shop_id == current_user.current_shop_id:
                content = request.form.get('note')
                title = content[:50] + ('...' if len(content) > 50 else '')
                note.title = title
                note.content = content
                db.session.commit()
                flash('Note updated successfully!', 'success')
            else:
                flash('You can only edit notes from your current shop!', 'error')

        elif 'delete_note' in request.form:
            note = Note.query.get_or_404(request.form.get('note_id'))
            if note.user_id == current_user.id and note.shop_id == current_user.current_shop_id:
                db.session.delete(note)
                db.session.commit()
                flash('Note deleted successfully!', 'success')
            else:
                flash('You can only delete notes from your current shop!', 'error')

        return redirect(url_for('notes.note_list'))

    # GET request
    page = request.args.get('page', 1, type=int)
    per_page = 9  # For a 3x3 grid layout

    query = Note.query
    show_all = request.args.get('show_all')

    if not show_all:
        # Filter by both user_id and shop_id
        query = query.filter(
            Note.user_id == current_user.id,
            Note.shop_id == current_user.current_shop_id
        )
    else:
        # When showing all, still filter by shop_id
        query = query.filter(Note.shop_id == current_user.current_shop_id)

    notes = query.order_by(desc(Note.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('notes/notes.html', notes=notes, show_all=show_all)