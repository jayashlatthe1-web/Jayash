import sqlite3
import json
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
import uuid
from datetime import datetime
import os

def get_db():
    print("DB PATH:", os.path.abspath(Config.DATABASE))
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db():
    """Add database constraints and indexes for seat booking, and migrate seat_number to TEXT for multiple seats"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if seat_number column exists and its type
        cursor.execute("PRAGMA table_info(bookings)")
        columns = cursor.fetchall()
        seat_col = next((col for col in columns if col[1] == 'seat_number'), None)
        
        # If seat_number is INTEGER, migrate to TEXT for JSON storage
        if seat_col and seat_col[2] == 'INTEGER':
            # Convert existing integer seat numbers to JSON format
            cursor.execute("SELECT id, seat_number FROM bookings WHERE seat_number IS NOT NULL")
            existing_bookings = cursor.fetchall()
            
            for booking in existing_bookings:
                booking_id, seat_num = booking
                # Convert single seat to JSON array format
                if seat_num:
                    cursor.execute(
                        "UPDATE bookings SET seat_number = ? WHERE id = ?",
                        (f"[{seat_num}]", booking_id)
                    )
            
            conn.commit()
        
        # Add Razorpay fields to payments table if they don't exist
        cursor.execute("PRAGMA table_info(payments)")
        payment_columns = [col[1] for col in cursor.fetchall()]
        
        if 'razorpay_order_id' not in payment_columns:
            try:
                cursor.execute("ALTER TABLE payments ADD COLUMN razorpay_order_id TEXT")
            except sqlite3.OperationalError:
                pass
        
        if 'razorpay_payment_id' not in payment_columns:
            try:
                cursor.execute("ALTER TABLE payments ADD COLUMN razorpay_payment_id TEXT")
            except sqlite3.OperationalError:
                pass
        
        if 'razorpay_signature' not in payment_columns:
            try:
                cursor.execute("ALTER TABLE payments ADD COLUMN razorpay_signature TEXT")
            except sqlite3.OperationalError:
                pass
        
        # Add gender column to students table if it doesn't exist
        cursor.execute("PRAGMA table_info(students)")
        student_columns = [col[1] for col in cursor.fetchall()]
        
        if 'gender' not in student_columns:
            try:
                cursor.execute("ALTER TABLE students ADD COLUMN gender TEXT")
            except sqlite3.OperationalError:
                pass
        
        conn.commit()
        
    except sqlite3.OperationalError as e:
        # Index might already exist, continue
        pass
    finally:
        conn.close()

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            class_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            city TEXT NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Admins table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Cities table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Routes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL,
            route_name TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (city_id) REFERENCES cities (id)
        )
    ''')
    
    # Buses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            bus_name TEXT NOT NULL,
            bus_number TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 50,
            FOREIGN KEY (route_id) REFERENCES routes (id)
        )
    ''')
    
    # Bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            bus_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            seat_number TEXT,
            booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (bus_id) REFERENCES buses (id),
            UNIQUE(student_id, academic_year)
        )
    ''')
    
    # Payments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            transaction_id TEXT UNIQUE,
            payment_date TIMESTAMP,
            status TEXT DEFAULT 'pending',
            verified_by INTEGER,
            verified_at TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings (id),
            FOREIGN KEY (verified_by) REFERENCES admins (id)
        )
    ''')
    
    
    conn.commit() 
    
    # Seed initial data
    seed_data(conn)
    conn.close()
    
    # Run migrations
    migrate_db()

def seed_data(conn):
    cursor = conn.cursor()
    
    # Check if admin exists
    cursor.execute('SELECT COUNT(*) FROM admins')
    if cursor.fetchone()[0] == 0:
        # Create default admin
        admin_password = generate_password_hash('admin123')
        cursor.execute(
            'INSERT INTO admins (username, email, password_hash) VALUES (?, ?, ?)',
            ('admin', 'admin@sgu.edu', admin_password)
        )
    
    # Seed cities
    cities = ['Kolhapur', 'Sangli', 'Miraj', 'Ichalkaranji', 'Satara', 'Karad']
    for city in cities:
        cursor.execute('INSERT OR IGNORE INTO cities (name) VALUES (?)', (city,))
    
    # Seed routes for each city (limited to 5 routes per city as per requirement)
    cursor.execute('SELECT id, name FROM cities')
    city_rows = cursor.fetchall()
    
    route_names = ['Route 1', 'Route 2', 'Route 3', 'Route 4', 'Route 5']
    
    for city in city_rows:
        for i in range(min(5, len(route_names))):  # Limited to 5 routes
            route_name = route_names[i]
            # Check if route already exists for this city
            cursor.execute('SELECT id FROM routes WHERE city_id = ? AND route_name = ?', (city['id'], route_name))
            if not cursor.fetchone():
                description = f"{city['name']} to SGU Campus via {route_name}"
                cursor.execute(
                    'INSERT INTO routes (city_id, route_name, description) VALUES (?, ?, ?)',
                    (city['id'], route_name, description)
                )
    
    # Seed buses for each route (1 bus per route)
    cursor.execute('SELECT r.id, r.route_name, c.name as city_name FROM routes r JOIN cities c ON r.city_id = c.id')
    routes = cursor.fetchall()
    
    for route in routes:
        # Check if bus already exists for this route
        cursor.execute('SELECT id FROM buses WHERE route_id = ?', (route['id'],))
        if not cursor.fetchone():
            # Create short form bus name like "Bus-KOP-1"
            city_name = route['city_name']
            city_short = 'KOP'  # Default to KOP for Kolhapur
            if 'Sangli' in city_name:
                city_short = 'SAN'
            elif 'Miraj' in city_name:
                city_short = 'MIR'
            elif 'Ichalkaranji' in city_name:
                city_short = 'ICH'
            elif 'Satara' in city_name:
                city_short = 'SAT'
            elif 'Karad' in city_name:
                city_short = 'KAR'
            
            bus_name = f"Bus-{city_short}-{route['id']}"
            bus_number = f"{city_short}-{route['id']}00"
            cursor.execute(
                'INSERT INTO buses (route_id, bus_name, bus_number, capacity) VALUES (?, ?, ?, ?)',
                (route['id'], bus_name, bus_number, 50)
            )
    
    conn.commit()

# Student operations
def create_student(full_name, email, password, class_name, year, city, phone=None):
    conn = get_db()
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute(
            '''INSERT INTO students (full_name, email, password_hash, class_name, year, city, phone)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (full_name, email, password_hash, class_name, year, city, phone)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_student_by_email(email):
    conn = get_db()
    student = conn.execute('SELECT * FROM students WHERE email = ?', (email,)).fetchone()
    conn.close()
    return student

def verify_student_password(email, password):
    student = get_student_by_email(email)
    if student and check_password_hash(student['password_hash'], password):
        return student
    return None

def get_student_by_id(student_id):
    conn = get_db()
    student = conn.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
    conn.close()
    return student

def update_student(student_id, class_name, year, phone):
    conn = get_db()
    conn.execute(
        'UPDATE students SET class_name = ?, year = ?, phone = ? WHERE id = ?',
        (class_name, year, phone, student_id)
    )
    conn.commit()
    conn.close()

# Admin operations
def get_admin_by_username(username):
    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
    conn.close()
    return admin

def verify_admin_password(username, password):
    admin = get_admin_by_username(username)
    if admin and check_password_hash(admin['password_hash'], password):
        return admin
    return None

# City, Route, Bus operations
def get_all_cities():
    conn = get_db()
    cities = conn.execute('SELECT * FROM cities ORDER BY name').fetchall()
    conn.close()
    return cities

def get_routes_by_city(city_id):
    """Get routes for a city, limited to 5 routes as per requirement"""
    conn = get_db()
    routes = conn.execute(
        'SELECT * FROM routes WHERE city_id = ? ORDER BY route_name LIMIT 5',
        (city_id,)
    ).fetchall()
    conn.close()
    return routes

def get_buses_by_route(route_id):
    """Get buses for a route - returns all buses (for admin use)"""
    conn = get_db()
    buses = conn.execute(
        'SELECT * FROM buses WHERE route_id = ? ORDER BY bus_name',
        (route_id,)
    ).fetchall()
    conn.close()
    return buses

def get_default_bus_for_route(route_id):
    """Get the default (first) bus assigned to a route"""
    conn = get_db()
    bus = conn.execute(
        'SELECT * FROM buses WHERE route_id = ? ORDER BY id LIMIT 1',
        (route_id,)
    ).fetchone()
    conn.close()
    return bus

def get_bus_by_id(bus_id):
    conn = get_db()
    bus = conn.execute('SELECT * FROM buses WHERE id = ?', (bus_id,)).fetchone()
    conn.close()
    return bus

def get_available_seats(bus_id, academic_year):
    conn = get_db()
    bus = conn.execute('SELECT capacity FROM buses WHERE id = ?', (bus_id,)).fetchone()
    booked = conn.execute(
        'SELECT COUNT(*) as count FROM bookings WHERE bus_id = ? AND academic_year = ? AND status IN (?, ?)',
        (bus_id, academic_year, 'pending_admin', 'confirmed')
    ).fetchone()
    conn.close()
    return bus['capacity'] - booked['count'] if bus else 0

def parse_seat_numbers(seat_data):
    """Parse seat numbers from database (comma-separated string or integer) to flat list of integers"""
    if seat_data is None or seat_data == '':
        return []
    if isinstance(seat_data, int):
        return [seat_data]
    if isinstance(seat_data, str):
        # Try JSON format first (for backward compatibility)
        try:
            parsed = json.loads(seat_data)
            # Normalize to flat list of integers
            result = []
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, (int, str)):
                        try:
                            result.append(int(item))
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(item, (list, tuple)):
                        result.extend([int(s) for s in item if isinstance(s, (int, str)) and str(s).isdigit()])
            elif isinstance(parsed, (int, str)):
                try:
                    result.append(int(parsed))
                except (ValueError, TypeError):
                    pass
            if result:
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Handle comma-separated string (new format)
        if ',' in seat_data:
            return [int(s.strip()) for s in seat_data.split(',') if s.strip().isdigit()]
        # Single number string
        try:
            return [int(seat_data.strip())]
        except ValueError:
            return []
    return []

def format_seat_numbers(seat_list):
    """Format list of seat numbers to comma-separated string for storage"""
    if not seat_list:
        return None
    # Sort and join with commas
    return ','.join(map(str, sorted(seat_list)))

def get_booked_seats(bus_id, academic_year, exclude_booking_id=None):
    """Get list of all booked seat numbers for a specific bus and academic year"""
    conn = get_db()
    if exclude_booking_id:
        bookings = conn.execute(
            '''SELECT seat_number FROM bookings 
               WHERE bus_id = ? AND academic_year = ? 
               AND seat_number IS NOT NULL
               AND id != ?
               AND status IN ('pending_admin', 'confirmed')''',
            (bus_id, academic_year, exclude_booking_id)
        ).fetchall()
    else:
        bookings = conn.execute(
            '''SELECT seat_number FROM bookings 
               WHERE bus_id = ? AND academic_year = ? 
               AND seat_number IS NOT NULL
               AND status IN ('pending_admin', 'confirmed')''',
            (bus_id, academic_year)
        ).fetchall()
    conn.close()
    
    # Flatten all seat numbers from all bookings
    booked_seats = []
    for row in bookings:
        seats = parse_seat_numbers(row['seat_number'])
        # Ensure all items are integers (flatten any nested lists)
        for seat in seats:
            if isinstance(seat, (list, tuple)):
                booked_seats.extend([int(s) for s in seat if isinstance(s, (int, str)) and str(s).isdigit()])
            elif isinstance(seat, (int, str)):
                try:
                    booked_seats.append(int(seat))
                except (ValueError, TypeError):
                    pass
    
    # Filter to ensure only integers and remove duplicates
    booked_seats = [s for s in booked_seats if isinstance(s, int) and s > 0]
    return sorted(set(booked_seats))  # Remove duplicates and sort

def get_booking_bus_id(booking_id):
    """Get bus_id for a specific booking"""
    conn = get_db()
    booking = conn.execute(
        'SELECT bus_id FROM bookings WHERE id = ?',
        (booking_id,)
    ).fetchone()
    conn.close()
    return booking['bus_id'] if booking else None

def save_seat_numbers(booking_id, seat_numbers_list, academic_year):
    """Save seat numbers as comma-separated string. Validates availability."""
    if not seat_numbers_list:
        return False, "No seat numbers provided"
    
    # Normalize seat_numbers_list to flat list of integers
    normalized_seats = []
    if isinstance(seat_numbers_list, (int, str)):
        try:
            normalized_seats = [int(seat_numbers_list)]
        except (ValueError, TypeError):
            normalized_seats = []
    elif isinstance(seat_numbers_list, (list, tuple)):
        for item in seat_numbers_list:
            if isinstance(item, (list, tuple)):
                normalized_seats.extend([int(s) for s in item if isinstance(s, (int, str)) and str(s).isdigit()])
            elif isinstance(item, (int, str)):
                try:
                    normalized_seats.append(int(item))
                except (ValueError, TypeError):
                    pass
    
    if not normalized_seats:
        return False, "No valid seat numbers provided"
    
    seat_numbers_list = normalized_seats
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current booking details
    booking = cursor.execute(
        'SELECT bus_id, seat_number FROM bookings WHERE id = ?',
        (booking_id,)
    ).fetchone()
    
    if not booking:
        conn.close()
        return False, "Booking not found"
    
    bus_id = booking['bus_id']
    
    # Validate seats are available (excluding current booking)
    available, unavailable = are_seats_available(bus_id, academic_year, seat_numbers_list, exclude_booking_id=booking_id)
    if not available:
        conn.close()
        return False, f"Seat(s) {unavailable} are already booked"
    
    # Format as comma-separated string
    seat_numbers_str = format_seat_numbers(seat_numbers_list)
    
    try:
        cursor.execute(
            'UPDATE bookings SET seat_number = ? WHERE id = ?',
            (seat_numbers_str, booking_id)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        conn.close()
        return False, str(e)

def are_seats_available(bus_id, academic_year, seat_numbers, exclude_booking_id=None):
    """Check if multiple seats are available. Returns (is_available, unavailable_seats)"""
    if not seat_numbers:
        return False, []
    
    # Normalize seat_numbers to flat list of integers
    normalized_seats = []
    for item in seat_numbers:
        if isinstance(item, (list, tuple)):
            normalized_seats.extend([int(s) for s in item if isinstance(s, (int, str)) and str(s).isdigit()])
        elif isinstance(item, (int, str)):
            try:
                normalized_seats.append(int(item))
            except (ValueError, TypeError):
                pass
    
    if not normalized_seats:
        return False, []
    
    seat_numbers = normalized_seats
    
    # Validate seat numbers are within bus capacity
    bus = get_bus_by_id(bus_id)
    if not bus:
        return False, seat_numbers
    
    capacity = bus['capacity']
    invalid_seats = [s for s in seat_numbers if not isinstance(s, int) or s < 1 or s > capacity]
    if invalid_seats:
        return False, invalid_seats
    
    # Get all booked seats for this bus
    booked_seats = get_booked_seats(bus_id, academic_year)
    
    # If updating, exclude seats from current booking
    if exclude_booking_id:
        conn = get_db()
        current_booking = conn.execute(
            'SELECT seat_number FROM bookings WHERE id = ?',
            (exclude_booking_id,)
        ).fetchone()
        conn.close()
        
        if current_booking:
            current_seats = parse_seat_numbers(current_booking['seat_number'])
            # Remove current booking's seats from booked list
            booked_seats = [s for s in booked_seats if s not in current_seats]
    
    # Check if any requested seat is already booked
    unavailable = [s for s in seat_numbers if s in booked_seats]
    
    return len(unavailable) == 0, unavailable

def is_seat_available(bus_id, academic_year, seat_number, exclude_booking_id=None):
    """Check if a single seat is available (backward compatibility)"""
    available, unavailable = are_seats_available(bus_id, academic_year, [seat_number], exclude_booking_id)
    return available

# Booking operations
# Booking operations
def check_existing_booking(student_id, academic_year):
    conn = get_db()
    booking = conn.execute(
        '''SELECT * FROM bookings
           WHERE student_id = ? AND academic_year = ?
           AND status IN ('pending_admin', 'confirmed')''',
        (student_id, academic_year)
    ).fetchone()
    conn.close()
    return booking


def create_pending_booking(student_id, bus_id, academic_year, seat_numbers=None):
    """Create a pending booking with optional seat numbers (list). Validates all seats availability."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Validate seats if provided
    if seat_numbers:
        # Normalize to flat list of integers
        normalized_seats = []
        if isinstance(seat_numbers, (int, str)):
            try:
                normalized_seats = [int(seat_numbers)]
            except (ValueError, TypeError):
                normalized_seats = []
        elif isinstance(seat_numbers, (list, tuple)):
            for item in seat_numbers:
                if isinstance(item, (list, tuple)):
                    normalized_seats.extend([int(s) for s in item if isinstance(s, (int, str)) and str(s).isdigit()])
                elif isinstance(item, (int, str)):
                    try:
                        normalized_seats.append(int(item))
                    except (ValueError, TypeError):
                        pass
        
        if normalized_seats:
            available, unavailable = are_seats_available(bus_id, academic_year, normalized_seats)
            if not available:
                conn.close()
                return None, f"Seat(s) {unavailable} are already booked or invalid"
            
            # Format seats as comma-separated string
            seat_data = format_seat_numbers(normalized_seats)
        else:
            seat_data = None
    else:
        seat_data = None
    
    try:
        cursor.execute(
            '''INSERT INTO bookings (student_id, bus_id, academic_year, seat_number, status)
               VALUES (?, ?, ?, ?, ?)''',
            (student_id, bus_id, academic_year, seat_data, 'pending_admin')
        )
        booking_id = cursor.lastrowid

        # Create payment record
        cursor.execute(
            '''INSERT INTO payments (booking_id, amount, status)
               VALUES (?, ?, ?)''',
            (booking_id, 12000.00, 'pending')
        )

        conn.commit()
        return booking_id, None
    except sqlite3.IntegrityError as e:
        conn.close()
        return None, "Booking already exists or seat conflict"
    finally:
        conn.close()

def confirm_seat(booking_id):
    """Confirm a booking - legacy function for admin seat confirmation"""
    conn = get_db()
    cursor = conn.cursor()

    booking = cursor.execute(
        'SELECT bus_id, academic_year, seat_number FROM bookings WHERE id = ?',
        (booking_id,)
    ).fetchone()
    
    if not booking:
        conn.close()
        return False

    # If seat already assigned, just update status
    if booking['seat_number']:
        cursor.execute(
            'UPDATE bookings SET status = ? WHERE id = ?',
            ('confirmed', booking_id)
        )
    else:
        # Auto-assign next available seat (legacy behavior)
        cursor.execute(
            '''SELECT COALESCE(MAX(seat_number), 0) + 1 as next_seat
               FROM bookings
               WHERE bus_id = ? AND academic_year = ? AND status = ?''',
            (booking['bus_id'], booking['academic_year'], 'confirmed')
        )
        seat_number = cursor.fetchone()['next_seat']

        cursor.execute(
            '''UPDATE bookings
               SET seat_number = ?, status = ?
               WHERE id = ?''',
            (seat_number, 'confirmed', booking_id)
        )

    conn.commit()
    conn.close()
    return True

def update_booking_seats(booking_id, new_seat_numbers, academic_year):
    """Update seat numbers for an existing booking. Validates availability."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current booking details
    booking = cursor.execute(
        'SELECT bus_id, seat_number FROM bookings WHERE id = ?',
        (booking_id,)
    ).fetchone()
    
    if not booking:
        conn.close()
        return False, "Booking not found"
    
    # Normalize seat numbers to flat list of integers
    normalized_seats = []
    if isinstance(new_seat_numbers, (int, str)):
        try:
            normalized_seats = [int(new_seat_numbers)]
        except (ValueError, TypeError):
            normalized_seats = []
    elif isinstance(new_seat_numbers, (list, tuple)):
        for item in new_seat_numbers:
            if isinstance(item, (list, tuple)):
                normalized_seats.extend([int(s) for s in item if isinstance(s, (int, str)) and str(s).isdigit()])
            elif isinstance(item, (int, str)):
                try:
                    normalized_seats.append(int(item))
                except (ValueError, TypeError):
                    pass
    
    if not normalized_seats:
        conn.close()
        return False, "No seat numbers provided"
    
    new_seat_numbers = normalized_seats
    
    # Format new seats
    new_seat_data = format_seat_numbers(new_seat_numbers)
    
    # Get current seats
    current_seats = parse_seat_numbers(booking['seat_number'])
    
    # If seats are unchanged, no need to validate
    if sorted(current_seats) == sorted(new_seat_numbers):
        conn.close()
        return True, None
    
    # Validate new seat availability (exclude current booking)
    available, unavailable = are_seats_available(
        booking['bus_id'], academic_year, new_seat_numbers, exclude_booking_id=booking_id
    )
    if not available:
        conn.close()
        return False, f"Seat(s) {unavailable} are already booked or invalid"
    
    try:
        cursor.execute(
            'UPDATE bookings SET seat_number = ? WHERE id = ?',
            (new_seat_data, booking_id)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        conn.close()
        return False, str(e)

def get_booking_details(student_id, academic_year):
    conn = get_db()
    booking = conn.execute('''
        SELECT b.*, 
               buses.bus_name, buses.bus_number,
               routes.route_name, routes.description as route_desc,
               cities.name as city_name,
               p.amount, p.transaction_id, p.payment_date, p.status as payment_status
        FROM bookings b
        JOIN buses ON b.bus_id = buses.id
        JOIN routes ON buses.route_id = routes.id
        JOIN cities ON routes.city_id = cities.id
        LEFT JOIN payments p ON b.id = p.booking_id
        WHERE b.student_id = ? AND b.academic_year = ?
    ''', (student_id, academic_year)).fetchone()
    conn.close()
    return booking

# Payment operations
def simulate_payment(booking_id):
    conn = get_db()
    transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
    conn.execute(
        '''UPDATE payments 
           SET status = ?, transaction_id = ?, payment_date = ?
           WHERE booking_id = ?''',
        ('paid', transaction_id, datetime.now(), booking_id)
    )
    conn.commit()
    conn.close()
    return transaction_id

def create_razorpay_order(booking_id, amount, currency='INR'):
    """Create a Razorpay order and store order_id"""
    import razorpay
    from config import Config
    
    # Validate API keys
    if not Config.RAZORPAY_KEY_ID or Config.RAZORPAY_KEY_ID == 'your-razorpay-key-id':
        raise ValueError('Razorpay Key ID is not configured')
    
    if not Config.RAZORPAY_KEY_SECRET or Config.RAZORPAY_KEY_SECRET == 'your-razorpay-key-secret':
        raise ValueError('Razorpay Key Secret is not configured')
    
    conn = get_db()
    client = razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
    
    try:
        # Create order in Razorpay
        order_data = {
            'amount': int(amount * 100),  # Convert to paise
            'currency': currency,
            'receipt': f'booking_{booking_id}',
            'notes': {
                'booking_id': booking_id
            }
        }
        razorpay_order = client.order.create(data=order_data)
        
        # Store order_id in database
        conn.execute(
            '''UPDATE payments 
               SET razorpay_order_id = ?
               WHERE booking_id = ?''',
            (razorpay_order['id'], booking_id)
        )
        conn.commit()
        conn.close()
        
        return razorpay_order
    except Exception as e:
        conn.close()
        raise e

def create_razorpay_qr_code(order_id, amount):
    """Create a Razorpay QR code for the order"""
    import razorpay
    from config import Config
    import time
    
    # Validate API keys
    if not Config.RAZORPAY_KEY_ID or Config.RAZORPAY_KEY_ID == 'your-razorpay-key-id':
        raise ValueError('Razorpay Key ID is not configured')
    
    if not Config.RAZORPAY_KEY_SECRET or Config.RAZORPAY_KEY_SECRET == 'your-razorpay-key-secret':
        raise ValueError('Razorpay Key Secret is not configured')
    
    client = razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
    
    try:
        # Create QR code for the order
        # Amount should be in paise (smallest currency unit)
        amount_in_paise = int(amount * 100)
        
        # QR code expires in 30 minutes (1800 seconds)
        close_by = int(time.time()) + 1800
        
        qr_data = {
            'type': 'upi_qr',
            'name': 'SGU Bus Enrollment',
            'usage': 'single_use',
            'fixed_amount': True,
            'payment_amount': amount_in_paise,
            'description': f'Bus Seat Booking Payment - Order {order_id}',
            'close_by': close_by,
            'notes': {
                'order_id': order_id,
                'purpose': 'Bus booking payment'
            }
        }
        
        # Create QR code using Razorpay API
        qr_code = client.qrcode.create(data=qr_data)
        
        return qr_code
    except Exception as e:
        # If QR code creation fails, return None (fallback to regular checkout)
        # This can happen if QR code feature is not enabled on the account
        print(f"QR code creation failed: {str(e)}")
        return None

def update_payment_with_razorpay(booking_id, razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Update payment record with Razorpay payment details"""
    conn = get_db()
    conn.execute(
        '''UPDATE payments 
           SET status = ?, 
               razorpay_payment_id = ?, 
               razorpay_order_id = ?, 
               razorpay_signature = ?,
               transaction_id = ?,
               payment_date = ?
           WHERE booking_id = ?''',
        ('paid', razorpay_payment_id, razorpay_order_id, razorpay_signature, 
         razorpay_payment_id, datetime.now(), booking_id)
    )
    conn.commit()
    conn.close()

def verify_razorpay_signature(order_id, payment_id, signature):
    """Verify Razorpay payment signature"""
    import razorpay
    from config import Config
    
    client = razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
    
    try:
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        client.utility.verify_payment_signature(params_dict)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
    except Exception:
        return False

def verify_payment(booking_id, admin_id):
    conn = get_db()
    conn.execute(
        '''UPDATE payments 
           SET status = ?, verified_by = ?, verified_at = ?
           WHERE booking_id = ?''',
        ('verified', admin_id, datetime.now(), booking_id)
    )
    conn.commit()
    conn.close()

def get_payment_by_booking(booking_id):
    conn = get_db()
    payment = conn.execute('SELECT * FROM payments WHERE booking_id = ?', (booking_id,)).fetchone()
    conn.close()
    return payment

# Admin dashboard stats
def get_dashboard_stats():
    conn = get_db()
    stats = {
        'total_students': conn.execute('SELECT COUNT(*) FROM students').fetchone()[0],
        'total_bookings': conn.execute(
            'SELECT COUNT(*) FROM bookings WHERE academic_year = ?',
            (Config.CURRENT_ACADEMIC_YEAR,)
        ).fetchone()[0],
        'pending_payments': conn.execute(
            '''SELECT COUNT(*) FROM payments p
               JOIN bookings b ON p.booking_id = b.id
               WHERE b.academic_year = ? AND p.status = ?''',
            (Config.CURRENT_ACADEMIC_YEAR, 'pending')
        ).fetchone()[0],
        'paid_payments': conn.execute(
            '''SELECT COUNT(*) FROM payments p
               JOIN bookings b ON p.booking_id = b.id
               WHERE b.academic_year = ? AND p.status = ?''',
            (Config.CURRENT_ACADEMIC_YEAR, 'paid')
        ).fetchone()[0],
        'verified_payments': conn.execute(
            '''SELECT COUNT(*) FROM payments p
               JOIN bookings b ON p.booking_id = b.id
               WHERE b.academic_year = ? AND p.status = ?''',
            (Config.CURRENT_ACADEMIC_YEAR, 'verified')
        ).fetchone()[0],
    }
    conn.close()
    return stats

def get_all_student_records():
    conn = get_db()
    records = conn.execute('''
        SELECT s.*, 
               b.id as booking_id, b.seat_number, b.booking_date, b.status as booking_status,
               buses.bus_name, buses.bus_number,
               routes.route_name,
               cities.name as city_name,
               p.amount, p.transaction_id, p.payment_date, p.status as payment_status
        FROM students s
        LEFT JOIN bookings b ON s.id = b.student_id AND b.academic_year = ?
        LEFT JOIN buses ON b.bus_id = buses.id
        LEFT JOIN routes ON buses.route_id = routes.id
        LEFT JOIN cities ON routes.city_id = cities.id
        LEFT JOIN payments p ON b.id = p.booking_id
        ORDER BY s.created_at DESC
    ''', (Config.CURRENT_ACADEMIC_YEAR,)).fetchall()
    conn.close()
    return records

def get_student_full_details(student_id):
    conn = get_db()
    record = conn.execute('''
        SELECT s.*, 
               b.id as booking_id, b.seat_number, b.booking_date, b.academic_year,
               buses.bus_name, buses.bus_number,
               routes.route_name, routes.description as route_desc,
               cities.name as city_name,
               p.id as payment_id, p.amount, p.transaction_id, p.payment_date, p.status as payment_status
        FROM students s
        LEFT JOIN bookings b ON s.id = b.student_id AND b.academic_year = ?
        LEFT JOIN buses ON b.bus_id = buses.id
        LEFT JOIN routes ON buses.route_id = routes.id
        LEFT JOIN cities ON routes.city_id = cities.id
        LEFT JOIN payments p ON b.id = p.booking_id
        WHERE s.id = ?
    ''', (Config.CURRENT_ACADEMIC_YEAR, student_id)).fetchone()
    conn.close()
    return record

def get_seat_categories():
    """Get seat category definitions for a bus"""
    return {
        'staff': {'seats': [1, 2], 'color': 'blue', 'label': 'Staff'},
        'boys': {'seats': list(range(3, 27)), 'color': 'green', 'label': 'Boys'},  # Seats 3-26 (24 seats)
        'girls': {'seats': list(range(27, 51)), 'color': 'pink', 'label': 'Girls'}  # Seats 27-50 (24 seats, but requirement says 25 - adjusting)
    }

def get_seat_category(seat_number):
    """Get the category for a specific seat number"""
    categories = get_seat_categories()
    for category, data in categories.items():
        if seat_number in data['seats']:
            return category, data
    return None, None

def get_seat_distribution(bus_id, academic_year):
    """Get seat distribution statistics for a bus"""
    categories = get_seat_categories()
    bus = get_bus_by_id(bus_id)
    if not bus:
        return None
    
    capacity = bus['capacity']
    booked_seats = get_booked_seats(bus_id, academic_year)
    
    distribution = {
        'total_seats': capacity,
        'booked_seats': len(booked_seats),
        'available_seats': capacity - len(booked_seats),
        'categories': {}
    }
    
    for category, data in categories.items():
        category_seats = data['seats']
        booked_in_category = len([s for s in booked_seats if s in category_seats])
        available_in_category = len(category_seats) - booked_in_category
        
        distribution['categories'][category] = {
            'total': len(category_seats),
            'booked': booked_in_category,
            'available': available_in_category,
            'color': data['color'],
            'label': data['label']
        }
    
    return distribution

def validate_seat_assignment(seat_numbers, student_gender=None):
    """Validate seat assignment based on seat categories and student gender"""
    if not seat_numbers:
        return True, None  # No seats assigned yet
    
    categories = get_seat_categories()
    
    for seat in seat_numbers:
        category, data = get_seat_category(seat)
        if not category:
            return False, f"Seat {seat} does not exist"
        
        # Check gender restrictions
        if student_gender:
            if category == 'staff' and student_gender.lower() != 'staff':
                return False, f"Seat {seat} is reserved for staff only"
            elif category == 'boys' and student_gender.lower() not in ['male', 'boy', 'm']:
                return False, f"Seat {seat} is reserved for boys only"
            elif category == 'girls' and student_gender.lower() not in ['female', 'girl', 'f']:
                return False, f"Seat {seat} is reserved for girls only"
    
    return True, None
