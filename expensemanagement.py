from models import db, Expense

VALID_CATEGORIES = {'food', 'travel', 'entertainment', 'shopping', 'other'}

def get_user_expenses(user_id: int):
    """
    Retrieves the latest expense record and total for a user.
    
    :param user_id: User's database ID
    :return: tuple (expense_data: dict, total: int)
    """
    latest = Expense.query.filter_by(user_id=user_id).order_by(Expense.created_at.desc()).first()

    if not latest:
        expense_data = {
            'food': 0,
            'travel': 0,
            'entertainment': 0,
            'shopping': 0,
            'other': 0
        }
    else:
        expense_data = {
            'id': latest.id,
            'food': int(latest.food or 0),
            'travel': int(latest.travel or 0),
            'entertainment': int(latest.entertainment or 0),
            'shopping': int(latest.shopping or 0),
            'other': int(latest.other or 0),
            'created_at': latest.created_at.isoformat() if latest.created_at else None
        }

    total = sum([
        expense_data['food'],
        expense_data['travel'],
        expense_data['entertainment'],
        expense_data['shopping'],
        expense_data['other']
    ])

    return expense_data, total


def add_user_expense(user_id: int, amount: int, category: str):
    """
    Adds an expense amount to the specified category and creates a new expense snapshot.
    
    :param user_id: User's database ID
    :param amount: Amount to add (must be > 0)
    :param category: One of ['food', 'travel', 'entertainment', 'shopping', 'other']
    :return: tuple (expense_data: dict, total: int, message: str)
    """
    category = (category or '').strip().lower()

    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")

    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Allowed: {', '.join(sorted(VALID_CATEGORIES))}")

    latest = Expense.query.filter_by(user_id=user_id).order_by(Expense.created_at.desc()).first()

    food = int(latest.food if latest else 0)
    travel = int(latest.travel if latest else 0)
    entertainment = int(latest.entertainment if latest else 0)
    shopping = int(latest.shopping if latest else 0)
    other = int(latest.other if latest else 0)

    if category == 'food':
        food += amount
    elif category == 'travel':
        travel += amount
    elif category == 'entertainment':
        entertainment += amount
    elif category == 'shopping':
        shopping += amount
    elif category == 'other':
        other += amount

    new_record = Expense(
        user_id=user_id,
        food=food,
        travel=travel,
        entertainment=entertainment,
        shopping=shopping,
        other=other
    )

    db.session.add(new_record)
    db.session.commit()

    updated_data = {
        'id': new_record.id,
        'food': food,
        'travel': travel,
        'entertainment': entertainment,
        'shopping': shopping,
        'other': other,
        'created_at': new_record.created_at.isoformat() if new_record.created_at else None
    }
    total = sum([food, travel, entertainment, shopping, other])
    message = f"Added ₹{amount:,} to {category.capitalize()}!"

    return updated_data, total, message


def delete_user_expense(user_id: int, amount: int, category: str):
    """
    Deducts an expense amount from the specified category and creates a new expense snapshot.
    
    :param user_id: User's database ID
    :param amount: Amount to deduct (must be > 0)
    :param category: One of ['food', 'travel', 'entertainment', 'shopping', 'other']
    :return: tuple (expense_data: dict, total: int, message: str)
    """
    category = (category or '').strip().lower()

    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")

    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Allowed: {', '.join(sorted(VALID_CATEGORIES))}")

    latest = Expense.query.filter_by(user_id=user_id).order_by(Expense.created_at.desc()).first()

    if not latest:
        raise ValueError("No expense records found to deduct from.")

    food = int(latest.food or 0)
    travel = int(latest.travel or 0)
    entertainment = int(latest.entertainment or 0)
    shopping = int(latest.shopping or 0)
    other = int(latest.other or 0)

    category_map = {
        'food': food,
        'travel': travel,
        'entertainment': entertainment,
        'shopping': shopping,
        'other': other
    }

    current_val = category_map[category]
    if current_val < amount:
        raise ValueError(f"Cannot delete ₹{amount:,}. Only ₹{current_val:,} available in {category.capitalize()}.")

    if category == 'food':
        food -= amount
    elif category == 'travel':
        travel -= amount
    elif category == 'entertainment':
        entertainment -= amount
    elif category == 'shopping':
        shopping -= amount
    elif category == 'other':
        other -= amount

    new_record = Expense(
        user_id=user_id,
        food=food,
        travel=travel,
        entertainment=entertainment,
        shopping=shopping,
        other=other
    )

    db.session.add(new_record)
    db.session.commit()

    updated_data = {
        'id': new_record.id,
        'food': food,
        'travel': travel,
        'entertainment': entertainment,
        'shopping': shopping,
        'other': other,
        'created_at': new_record.created_at.isoformat() if new_record.created_at else None
    }
    total = sum([food, travel, entertainment, shopping, other])
    message = f"Deducted ₹{amount:,} from {category.capitalize()}."

    return updated_data, total, message
