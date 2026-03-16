import sys
import traceback

try:
    from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
    from flask_mail import Mail, Message
    from functools import wraps
    from config import Config
    import models
    import json
except Exception as e:
    sys.stderr.write('\nERROR: Failed to import required modules.\n')
    sys.stderr.write(f'Cause: {e}\n')
    tb = traceback.format_exc()
    sys.stderr.write(tb + '\n')
    sys.stderr.write('Active Python executable: ' + sys.executable + '\n')
    sys.stderr.write('\nMost likely you are running the system Python which does not have the project\n')
    sys.stderr.write('dependencies installed. To run the app using the project virtualenv, do:\n')
    sys.stderr.write('  PowerShell:\n')
    sys.stderr.write('    .\\.venv\\Scripts\\python.exe app.py\n')
    sys.stderr.write('  or activate and run:\n')
    sys.stderr.write('    .\\.venv\\Scripts\\Activate.ps1\n')
    sys.stderr.write('    python app.py\n')
    sys.stderr.write('\nIf you do not have a virtualenv yet, create and install requirements:\n')
    sys.stderr.write('    python -m venv .venv\n')
    sys.stderr.write('    .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n')
    sys.stderr.write('\nAlternatively use the provided run.ps1 or run.bat scripts in the project root.\n')
    sys.exit(1)

app = Flask(__name__)
app.config.from_object(Config)
mail = Mail(app)

# Template filter to format seat numbers
@app.template_filter('format_seats')
def format_seats_filter(seat_data):
    """Format seat numbers from database for display (comma-separated)"""
    if not seat_data:
        return None
    seats = models.parse_seat_numbers(seat_data)
    if not seats:
        return None
    return ', '.join(map(str, sorted(seats)))

# Decorators for authentication
def student_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access the admin panel.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Landing page
@app.route('/')
def index():
    return render_template('index.html')

# Student routes
@app.route('/student/signup', methods=['GET', 'POST'])
def student_signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        class_name = request.form.get('class_name', '').strip()
        year = request.form.get('year', type=int)
        city = request.form.get('city', '').strip()
        phone = request.form.get('phone', '').strip() or None
        
        # Validation
        if not all([full_name, email, password, class_name, year, city]):
            flash('Please fill in all required fields.', 'danger')
            return render_template('student/signup.html', cities=models.get_all_cities())
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('student/signup.html', cities=models.get_all_cities())
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('student/signup.html', cities=models.get_all_cities())
        
        # Create student
        student_id = models.create_student(full_name, email, password, class_name, year, city, phone)
        
        if student_id:
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('student_login'))
        else:
            flash('An account with this email already exists.', 'danger')
    
    cities = models.get_all_cities()
    return render_template('student/signup.html', cities=cities)

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        student = models.verify_student_password(email, password)
        
        if student:
            session['student_id'] = student['id']
            session['student_name'] = student['full_name']
            flash(f'Welcome back, {student["full_name"]}!', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('student/login.html')

@app.route('/student/logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/student/dashboard')
@student_login_required
def student_dashboard():
    student = models.get_student_by_id(session['student_id'])
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    return render_template('student/dashboard.html', 
                         student=student, 
                         booking=booking,
                         academic_year=Config.CURRENT_ACADEMIC_YEAR)

@app.route('/student/profile', methods=['GET', 'POST'])
@student_login_required
def student_profile():
    student = models.get_student_by_id(session['student_id'])
    
    if request.method == 'POST':
        class_name = request.form.get('class_name', '').strip()
        year = request.form.get('year', type=int)
        phone = request.form.get('phone', '').strip() or None
        
        models.update_student(session['student_id'], class_name, year, phone)
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student_profile'))
    
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    return render_template('student/profile.html', student=student, booking=booking)

@app.route('/student/bus-selection')
@student_login_required
def bus_selection():
    # Check if already booked
    existing_booking = models.check_existing_booking(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    if existing_booking:
        flash('You have already booked a seat for this academic year.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    cities = models.get_all_cities()
    return render_template('student/bus_selection.html', cities=cities)

@app.route('/api/routes/<int:city_id>')
@student_login_required
def get_routes(city_id):
    """Get routes for a city (limited to 6) with bus information"""
    routes = models.get_routes_by_city(city_id)
    result = []
    for route in routes:
        # Get default bus for this route
        bus = models.get_default_bus_for_route(route['id'])
        if bus:
            available_seats = models.get_available_seats(bus['id'], Config.CURRENT_ACADEMIC_YEAR)
            result.append({
                'id': route['id'],
                'route_name': route['route_name'],
                'description': route['description'],
                'bus_id': bus['id'],
                'bus_name': bus['bus_name'],
                'bus_number': bus['bus_number'],
                'capacity': bus['capacity'],
                'available_seats': available_seats
            })
    return jsonify(result)

@app.route('/api/buses/<int:route_id>')
@student_login_required
def get_buses(route_id):
    buses = models.get_buses_by_route(route_id)
    result = []
    for bus in buses:
        available = models.get_available_seats(bus['id'], Config.CURRENT_ACADEMIC_YEAR)
        result.append({
            'id': bus['id'],
            'bus_name': bus['bus_name'],
            'bus_number': bus['bus_number'],
            'capacity': bus['capacity'],
            'available_seats': available
        })
    return jsonify(result)

@app.route('/api/booked-seats/<int:bus_id>')
@student_login_required
def get_booked_seats_api(bus_id):
    """API endpoint to get booked seats for a bus"""
    booked_seats = models.get_booked_seats(bus_id, Config.CURRENT_ACADEMIC_YEAR)
    bus = models.get_bus_by_id(bus_id)
    if not bus:
        return jsonify({'error': 'Bus not found'}), 404
    
    return jsonify({
        'booked_seats': booked_seats,
        'capacity': bus['capacity']
    })

@app.route('/api/seat-distribution/<int:bus_id>')
@admin_login_required
def get_seat_distribution_api(bus_id):
    """API endpoint to get seat distribution for a bus"""
    distribution = models.get_seat_distribution(bus_id, Config.CURRENT_ACADEMIC_YEAR)
    if not distribution:
        return jsonify({'error': 'Bus not found'}), 404
    
    return jsonify(distribution)

@app.route('/api/booking-seats/<int:booking_id>')
@admin_login_required
def get_booking_seats_api(booking_id):
    """API endpoint to get booked seats for a booking's bus (admin)"""
    conn = models.get_db()
    booking = conn.execute(
        'SELECT bus_id, seat_number FROM bookings WHERE id = ?',
        (booking_id,)
    ).fetchone()
    conn.close()
    
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404
    
    bus_id = booking['bus_id']
    current_seats = models.parse_seat_numbers(booking['seat_number'])
    booked_seats = models.get_booked_seats(bus_id, Config.CURRENT_ACADEMIC_YEAR, exclude_booking_id=booking_id)
    bus = models.get_bus_by_id(bus_id)
    
    if not bus:
        return jsonify({'error': 'Bus not found'}), 404
    
    return jsonify({
        'booked_seats': booked_seats,
        'current_seats': current_seats,
        'capacity': bus['capacity'],
        'bus_id': bus_id
    })

@app.route('/admin/save-seat-numbers/<int:booking_id>', methods=['POST'])
@admin_login_required
def admin_save_seat_numbers(booking_id):
    """Admin route to save seat numbers from modal"""
    data = request.get_json()
    seat_numbers = data.get('seat_numbers', [])
    
    if not seat_numbers or not isinstance(seat_numbers, list):
        return jsonify({'success': False, 'error': 'Invalid seat numbers'}), 400
    
    if len(seat_numbers) == 0:
        return jsonify({'success': False, 'error': 'At least one seat must be selected'}), 400
    
    success, error = models.save_seat_numbers(booking_id, seat_numbers, Config.CURRENT_ACADEMIC_YEAR)
    
    if success:
        return jsonify({'success': True, 'message': 'Seat numbers saved successfully'})
    else:
        return jsonify({'success': False, 'error': error}), 400

@app.route('/student/continue', methods=['POST'])
@student_login_required
def student_continue():
    route_id = request.form.get('route_id', type=int)

    if not route_id:
        flash('Please select a route.', 'danger')
        return redirect(url_for('bus_selection'))

    # Get the default bus for the selected route
    bus = models.get_default_bus_for_route(route_id)
    
    if not bus:
        flash('No bus available for the selected route. Please contact admin.', 'danger')
        return redirect(url_for('bus_selection'))

    # Create booking without seat numbers - seats will be assigned by admin
    booking_id, error = models.create_pending_booking(
        session['student_id'],
        bus['id'],
        Config.CURRENT_ACADEMIC_YEAR,
        seat_numbers=None  # No seat selection - admin will assign
    )
    
    if booking_id:
        flash('Bus booking created successfully! Please proceed to payment.', 'success')
        return redirect(url_for('payment_page'))
    else:
        flash(error or 'An error occurred. Please try again.', 'danger')
        return redirect(url_for('bus_selection'))

@app.route('/student/payment')
@student_login_required
def payment_page():
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    student = models.get_student_by_id(session['student_id'])
    
    if not booking:
        flash('No booking found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    if booking['payment_status'] == 'paid' or booking['payment_status'] == 'verified':
        flash('Payment has already been processed.', 'info')
        return redirect(url_for('student_dashboard'))
    
    return render_template('student/payment.html', 
                         booking=booking, 
                         student=student,
                         razorpay_key_id=Config.RAZORPAY_KEY_ID,
                         razorpay_only=Config.RAZORPAY_ONLY)

@app.route('/api/create-razorpay-order', methods=['POST'])
@student_login_required
def create_razorpay_order():
    """Create Razorpay order for payment"""
    # Check if Razorpay keys are configured
    if Config.RAZORPAY_KEY_ID == 'your-razorpay-key-id' or Config.RAZORPAY_KEY_SECRET == 'your-razorpay-key-secret':
        return jsonify({
            'error': 'Razorpay API keys are not configured. Please set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in your environment variables or config.py'
        }), 500
    
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    
    if not booking:
        return jsonify({'error': 'No booking found'}), 404
    
    if booking['payment_status'] in ['paid', 'verified']:
        return jsonify({'error': 'Payment already processed'}), 400
    
    try:
        amount = float(booking['amount'])
        razorpay_order = models.create_razorpay_order(booking['id'], amount)
        
        # Try to create QR code for the order
        qr_code = models.create_razorpay_qr_code(razorpay_order['id'], amount)
        
        response_data = {
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'key_id': Config.RAZORPAY_KEY_ID
        }
        
        # Add QR code data if available
        if qr_code:
            response_data['qr_code'] = {
                'id': qr_code.get('id'),
                'image_url': qr_code.get('image_url') or qr_code.get('short_url'),
                'short_url': qr_code.get('short_url'),
                'image_content': qr_code.get('image_content')  # Base64 encoded image
            }
        
        return jsonify(response_data)
    except Exception as e:
        error_msg = str(e)
        # Provide more helpful error messages
        if 'Authentication failed' in error_msg or '401' in error_msg:
            return jsonify({
                'error': 'Razorpay authentication failed. Please check your API keys (Key ID and Key Secret) are correct.'
            }), 500
        return jsonify({'error': error_msg}), 500

@app.route('/student/payment-success', methods=['POST'])
@student_login_required
def payment_success():
    """Handle successful Razorpay payment"""
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    
    if not booking:
        flash('No booking found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Get payment details from Razorpay response
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_signature = request.form.get('razorpay_signature')
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        flash('Invalid payment details.', 'danger')
        return redirect(url_for('payment_page'))
    
    # Verify signature
    is_valid = models.verify_razorpay_signature(
        razorpay_order_id, 
        razorpay_payment_id, 
        razorpay_signature
    )
    
    if not is_valid:
        flash('Payment verification failed. Please contact support.', 'danger')
        return redirect(url_for('payment_page'))
    
    # Update payment record
    models.update_payment_with_razorpay(
        booking['id'],
        razorpay_payment_id,
        razorpay_order_id,
        razorpay_signature
    )
    
    flash('Payment successful! Your booking is confirmed.', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/payment-failure')
@student_login_required
def payment_failure():
    """Handle failed Razorpay payment"""
    error_code = request.args.get('error[code]', '')
    error_description = request.args.get('error[description]', 'Payment was cancelled or failed')
    
    flash(f'Payment failed: {error_description}', 'danger')
    return redirect(url_for('payment_page'))

@app.route('/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    """Handle Razorpay webhook events"""
    import hmac
    import hashlib
    
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    webhook_secret = Config.RAZORPAY_WEBHOOK_SECRET
    
    if not webhook_signature:
        return jsonify({'error': 'Missing signature'}), 400
    
    # Verify webhook signature
    payload = request.get_data(as_text=True)
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(webhook_signature, expected_signature):
        return jsonify({'error': 'Invalid signature'}), 400
    
    event = request.get_json()
    event_type = event.get('event')
    
    if event_type == 'payment.captured':
        payment_data = event.get('payload', {}).get('payment', {}).get('entity', {})
        order_data = event.get('payload', {}).get('order', {}).get('entity', {})
        
        order_id = order_data.get('id')
        payment_id = payment_data.get('id')
        
        if order_id and payment_id:
            # Find booking by order_id
            conn = models.get_db()
            payment = conn.execute(
                'SELECT booking_id FROM payments WHERE razorpay_order_id = ?',
                (order_id,)
            ).fetchone()
            conn.close()
            
            if payment:
                booking_id = payment['booking_id']
                # Update payment status
                models.update_payment_with_razorpay(
                    booking_id,
                    payment_id,
                    order_id,
                    ''  # Signature not available in webhook
                )
    
    return jsonify({'status': 'success'}), 200

# Keep simulate payment for testing (optional)
@app.route('/student/simulate-payment', methods=['POST'])
@student_login_required
def simulate_payment():
    """Simulate payment for testing (development only)"""
    booking = models.get_booking_details(session['student_id'], Config.CURRENT_ACADEMIC_YEAR)
    
    if not booking:
        flash('No booking found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    if booking['payment_status'] != 'pending':
        flash('Payment has already been processed.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    transaction_id = models.simulate_payment(booking['id'])
    flash(f'Payment simulated! Transaction ID: {transaction_id}', 'success')
    return redirect(url_for('student_dashboard'))

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')

        # --- FIXED (hard-coded admin credentials) ---
        if username == "admin" and password == "admin123":
            session['admin_id'] = 1
            session['admin_username'] = "admin"
            flash('Welcome, admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        # -------------------------------------------

        flash('Invalid credentials.', 'danger')

    return render_template('admin/login.html')
# --- Seat Confirmation Route ---
@app.route('/admin/confirm-seat/<int:booking_id>', methods=['POST'])
@admin_login_required
def admin_confirm_seat(booking_id):
    try:
        models.confirm_seat(booking_id)
        flash('Seat confirmed successfully!', 'success')
    except Exception as e:
        flash(f'Error confirming seat: {str(e)}', 'danger')
    return redirect(request.referrer or url_for('admin_students'))



@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    stats = models.get_dashboard_stats()
    return render_template('admin/dashboard.html', stats=stats, academic_year=Config.CURRENT_ACADEMIC_YEAR)

@app.route('/admin/students')
@admin_login_required
def admin_students():
    records = models.get_all_student_records()  # <- हे records मिळत आहेत का?
    return render_template('admin/students.html', records=records, academic_year=Config.CURRENT_ACADEMIC_YEAR)

@app.route('/admin/student/<int:student_id>')
@admin_login_required
def admin_student_detail(student_id):
    record = models.get_student_full_details(student_id)
    if not record:
        flash('Student not found.', 'danger')
        return redirect(url_for('admin_students'))
    return render_template('admin/student_detail.html', record=record)

@app.route('/admin/verify-payment/<int:booking_id>', methods=['POST'])
@admin_login_required
def admin_verify_payment(booking_id):
    models.verify_payment(booking_id, session['admin_id'])
    flash('Payment verified successfully!', 'success')
    return redirect(request.referrer or url_for('admin_students'))

@app.route('/admin/update-seat/<int:booking_id>', methods=['POST'])
@admin_login_required
def admin_update_seat(booking_id):
    """Admin route to update seat numbers for a booking"""
    seat_numbers_json = request.form.get('seat_numbers', '')
    
    if not seat_numbers_json:
        flash('Please provide valid seat numbers.', 'danger')
        return redirect(request.referrer or url_for('admin_students'))
    
    # Parse seat numbers from JSON or comma-separated string
    try:
        import json
        try:
            seat_numbers = json.loads(seat_numbers_json)
        except json.JSONDecodeError:
            # Try comma-separated format
            seat_numbers = [int(s.strip()) for s in seat_numbers_json.split(',') if s.strip().isdigit()]
        
        if not isinstance(seat_numbers, list) or len(seat_numbers) == 0:
            flash('Invalid seat numbers. Please provide a comma-separated list.', 'danger')
            return redirect(request.referrer or url_for('admin_students'))
    except (ValueError, TypeError):
        flash('Invalid seat number format.', 'danger')
        return redirect(request.referrer or url_for('admin_students'))
    
    success, error = models.update_booking_seats(booking_id, seat_numbers, Config.CURRENT_ACADEMIC_YEAR)
    
    if success:
        flash(f'Seat numbers updated successfully!', 'success')
    else:
        flash(error or 'Failed to update seat numbers.', 'danger')
    
    return redirect(request.referrer or url_for('admin_students'))

@app.route('/admin/send-receipt/<int:student_id>', methods=['POST'])
@admin_login_required
def send_receipt(student_id):
    record = models.get_student_full_details(student_id)
    
    if not record or not record['booking_id']:
        flash('No booking found for this student.', 'danger')
        return redirect(url_for('admin_student_detail', student_id=student_id))
    
    if record['payment_status'] != 'verified':
        flash('Payment must be verified before sending receipt.', 'warning')
        return redirect(url_for('admin_student_detail', student_id=student_id))
    
    try:
        msg = Message(
            subject='SGU Bus Enrollment - Payment Receipt',
            recipients=[record['email']]
        )
        msg.html = f'''
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a365d; color: white; padding: 20px; text-align: center;">
                <h1>SGU Bus Enrollment</h1>
                <p>Payment Receipt</p>
            </div>
            <div style="padding: 20px;">
                <h2>Dear {record['full_name']},</h2>
                <p>Your bus enrollment payment has been verified. Here are your booking details:</p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr style="background: #f0f0f0;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Student Name</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['full_name']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Email</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['email']}</td>
                    </tr>
                    <tr style="background: #f0f0f0;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>City</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['city_name']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Route</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['route_name']}</td>
                    </tr>
                    <tr style="background: #f0f0f0;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Bus</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['bus_name']} ({record['bus_number']})</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Seat(s)</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{', '.join(map(str, models.parse_seat_numbers(record['seat_number']))) if record['seat_number'] else 'Not assigned'}</td>
                    </tr>
                    <tr style="background: #f0f0f0;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Academic Year</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['academic_year']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Amount Paid</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">₹{record['amount']}</td>
                    </tr>
                    <tr style="background: #f0f0f0;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Transaction ID</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['transaction_id']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Payment Date</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{record['payment_date']}</td>
                    </tr>
                </table>
                
                <p style="color: green; font-weight: bold;">✓ Your seat has been confirmed for the academic year {record['academic_year']}.</p>
                
                <p>Thank you for enrolling in SGU Campus Bus Service.</p>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated email. Please do not reply to this message.<br>
                    Sanjay Ghodawat University - Transport Department
                </p>
            </div>
        </body>
        </html>
        '''
        mail.send(msg)
        flash('Payment receipt sent successfully!', 'success')
    except Exception as e:
        flash(f'Failed to send email: {str(e)}', 'danger')
    
    return redirect(url_for('admin_student_detail', student_id=student_id))

if __name__ == '__main__':
    models.init_db()
    app.run(debug=True)
