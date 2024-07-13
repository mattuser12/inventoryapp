from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_httpauth import HTTPDigestAuth
from flask_digest import Stomach
import sqlite3

app = Flask(__name__)

DATABASE = '/home/ec2-user/inventory.db'

@app.route('/')
def index():
    return send_from_directory('/var/www/html', 'index.html')


stomach = Stomach('realm')

db = dict()

@stomach.register
def add_user(username, password):
    db[username] = password

@stomach.access
def get_user(username):
    return db.get(username, None)

@app.route('/secret')
@stomach.protect
def main():
    return 'SUCCESS'

add_user('aws', 'candidate')


@app.route('/v1/stocks', methods=['POST'])
def create_or_update_item():
    data = request.get_json()
    name = data.get('name')
    amount = data.get('amount', 0)

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    # Validate that amount is an integer
    if not isinstance(amount, int):
        return jsonify({'message': 'ERROR'}), 400

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if the item already exists
        cursor.execute('SELECT amount FROM inventory WHERE name = ?', (name,))
        row = cursor.fetchone()

        if row:
            # Fetch current amount and update with proper addition
            current_amount = row[0]
            new_amount = current_amount + amount
            cursor.execute('''
                UPDATE inventory SET amount = ? WHERE name = ?
            ''', (new_amount, name))
            conn.commit()
            return jsonify({'name': name, 'amount': new_amount}), 200
        else:
            # Insert the item if it doesn't exist
            cursor.execute('''
                INSERT INTO inventory (name, amount) VALUES (?, ?)
            ''', (name, amount))
            conn.commit()
            return jsonify({'name': name, 'amount': amount}), 200
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@app.route('/v1/stocks/<name>', methods=['GET'])
def stock_check(name):
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Execute the SELECT statement to get the amount
        cursor.execute('SELECT amount FROM inventory WHERE name = ?', (name,))
        row = cursor.fetchone()

        if row:
            amount = row[0]
            return jsonify({name: amount}), 200
        else:
            return jsonify({'error': 'Item not found'}), 404

    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/v1/stocks', methods=['GET'])
def get_all_stocks():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Execute the SELECT statement to get all items
        cursor.execute('SELECT name, amount FROM inventory')
        rows = cursor.fetchall()

        # Format the response
        all_stocks = {row[0]: row[1] for row in rows}

        return jsonify(all_stocks), 200

    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

# Initialize a counter for total sales
total_sales = 0

@app.route('/v1/sales', methods=['POST'])
def sell_item():
    data = request.get_json()
    name = data.get('name')
    amount = data.get('amount', 1)  # default to 1 if amount is not provided
    price = data.get('price')  # optional price parameter

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if amount is not None and (not isinstance(amount, int) or amount <= 0):
        return jsonify({'error': 'Amount must be a positive integer'}), 400

    if price is not None and (not isinstance(price, (int, float)) or price <= 0):
        return jsonify({'error': 'Price must be a number greater than 0'}), 400

    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Execute the UPDATE statement to decrease the amount
        cursor.execute('''
            UPDATE inventory SET amount = amount - ? WHERE name = ?
        ''', (amount, name))

        # Check if any rows were affected
        if cursor.rowcount == 0:
            return jsonify({'error': 'Item not found'}), 404

        # Calculate total sale amount based on price (if provided)
        if price:
            total_sale_amount = amount * price
        else:
            total_sale_amount = amount

        # Update the 'sales' column in the inventory table
        cursor.execute('''
            UPDATE inventory SET sold = sold + ? WHERE name = ?
        ''', (total_sale_amount, name))

        # Commit the transaction
        conn.commit()

        # Update total sales counter
        global total_sales
        total_sales += total_sale_amount

        # Construct the response JSON
        response_data = {
            'name': name,
            'amount': amount,
        }
        if price:
            response_data['price'] = price

        # Construct the location header URL
        location_url = f"http://{request.host}/v1/sales/{name}"

        return jsonify(response_data), 200, {'Location': location_url}

    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@app.route('/v1/sales', methods=['GET'])
def get_total_sales():
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Execute query to get total sales amount
        cursor.execute('SELECT SUM(sold) FROM inventory')
        total_sales_amount = cursor.fetchone()[0]

        # Convert total_sales_amount to float
        total_sales_amount = float(total_sales_amount)

        # If there are no sales yet, return 0
        if total_sales_amount is None:
            total_sales_amount = 0

        # Construct response JSON
        response_data = {
            'sales': total_sales_amount
        }

        return jsonify(response_data), 200

    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/v1/stocks', methods=['DELETE'])
def delete_all_items():
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if there are any items in the inventory
        cursor.execute('SELECT COUNT(*) FROM inventory')
        count = cursor.fetchone()[0]

        if count == 0:
            return jsonify({'message': 'No items to delete'}), 200

        # Execute DELETE statement to remove all items
        cursor.execute('DELETE FROM inventory')

        # Commit the transaction
        conn.commit()

        return jsonify({'message': 'All items deleted successfully'}), 200

    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

