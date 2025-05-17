from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
import json
import re
from email.mime.text import MIMEText
import socket
import ssl
import time
import random
from email.mime.multipart import MIMEMultipart
import logging
from logging.handlers import RotatingFileHandler
import os

app = Flask(__name__)
CORS(app)

# Configure logging
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('SMTP Relay startup')

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_port(port):
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False

def get_connection_timeout():
    """Get a random timeout between 8-12 seconds to prevent connection hanging"""
    return random.uniform(8, 12)

def try_smtp_connection(server, port, username, password, from_email, to_email, msg, client_hostname=None, max_retries=2):
    """Try SMTP connection with specific configuration and retry logic"""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            timeout = get_connection_timeout()
            
            if port == 465:  # SSL port
                context = ssl.create_default_context()
                context.check_hostname = False  # Some servers have invalid certificates
                context.verify_mode = ssl.CERT_NONE
                
                with smtplib.SMTP_SSL(
                    server, 
                    port, 
                    timeout=timeout, 
                    local_hostname=client_hostname,
                    context=context
                ) as smtp:
                    # Try both EHLO and HELO
                    try:
                        smtp.ehlo()
                    except:
                        smtp.helo()
                    
                    smtp.login(username, password)
                    smtp.sendmail(from_email, to_email, msg.as_string())
                    return True, None
                    
            else:  # Other ports
                with smtplib.SMTP(
                    server, 
                    port, 
                    timeout=timeout, 
                    local_hostname=client_hostname
                ) as smtp:
                    # Try both EHLO and HELO
                    try:
                        smtp.ehlo()
                    except:
                        smtp.helo()
                    
                    if port in [587, 25]:  # Try STARTTLS for these ports
                        try:
                            smtp.starttls(context=ssl.create_default_context())
                            # Re-identify after STARTTLS
                            try:
                                smtp.ehlo()
                            except:
                                smtp.helo()
                        except Exception as e:
                            # Log but continue if STARTTLS fails
                            print(f"STARTTLS failed: {str(e)}")
                    
                    smtp.login(username, password)
                    smtp.sendmail(from_email, to_email, msg.as_string())
                    return True, None
                    
        except (smtplib.SMTPException, socket.error, ssl.SSLError) as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                # Exponential backoff between retries
                time.sleep(2 ** attempt)
                continue
                
    return False, last_error

def create_email_message(from_email, to_email, subject, body):
    """Create a more robust email message with both plain text and HTML versions"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    
    # Add plain text version
    text_part = MIMEText(body, 'plain', 'utf-8')
    msg.attach(text_part)
    
    # Add HTML version (simple conversion)
    html_body = body.replace('\n', '<br>')
    html_part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(html_part)
    
    return msg

@app.route('/api/send_email', methods=['POST', 'OPTIONS'])
def handle_email():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        if not data:
            app.logger.warning('No data provided in request')
            return jsonify({
                "error": "❌ FAILURE",
                "message": "No data provided"
            }), 400

        # Validate required fields
        required_fields = [
            'smtp_server',
            'smtp_port',
            'smtp_user',
            'smtp_password',
            'from_email',
            'to_email',
            'subject',
            'body'
        ]
        
        # Check for missing fields
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                "error": "❌ FAILURE",
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        # Extract and validate fields
        smtp_server = data['smtp_server'].strip()
        smtp_port = data['smtp_port']
        smtp_user = data['smtp_user'].strip()
        smtp_password = data['smtp_password']
        from_email = data['from_email'].strip()
        to_email = data['to_email'].strip()
        subject = data['subject'].strip()
        body = data['body'].strip()

        # Validate email addresses
        if not validate_email(from_email) or not validate_email(to_email):
            return jsonify({
                "error": "❌ FAILURE",
                "message": "Invalid email address format"
            }), 400

        # Validate port number
        if not validate_port(smtp_port):
            return jsonify({
                "error": "❌ FAILURE",
                "message": "Invalid port number. Must be between 1 and 65535"
            }), 400

        # Validate server address
        if not smtp_server or len(smtp_server) > 255:
            return jsonify({
                "error": "❌ FAILURE",
                "message": "Invalid SMTP server address"
            }), 400

        # Validate subject and body
        if not subject or len(subject) > 1000:
            return jsonify({
                "error": "❌ FAILURE",
                "message": "Invalid subject length"
            }), 400

        if not body or len(body) > 1000000:  # 1MB limit
            return jsonify({
                "error": "❌ FAILURE",
                "message": "Invalid body length"
            }), 400

        # Create email message
        msg = create_email_message(from_email, to_email, subject, body)

        # Try sending with the provided configuration first
        success, error = try_smtp_connection(
            smtp_server, 
            smtp_port, 
            smtp_user, 
            smtp_password, 
            from_email, 
            to_email, 
            msg
        )

        if success:
            return jsonify({
                "success": "✅ SUCCESS",
                "message": "Email sent successfully"
            }), 200

        # If initial attempt fails, try alternative configurations
        smtp_configs = [
            {'port': 465, 'use_ssl': True, 'client_hostname': None},
            {'port': 587, 'use_ssl': False, 'client_hostname': None},
            {'port': 25, 'use_ssl': False, 'client_hostname': None},
            {'port': 465, 'use_ssl': True, 'client_hostname': smtp_user},
            {'port': 587, 'use_ssl': False, 'client_hostname': smtp_user},
            {'port': 465, 'use_ssl': True, 'client_hostname': smtp_server},
            {'port': 587, 'use_ssl': False, 'client_hostname': smtp_server},
            {'port': 465, 'use_ssl': True, 'client_hostname': from_email.split('@')[1]},
            {'port': 587, 'use_ssl': False, 'client_hostname': from_email.split('@')[1]}
        ]

        for config in smtp_configs:
            if config['port'] == smtp_port:  # Skip if it's the same as the original attempt
                continue
                
            success, error = try_smtp_connection(
                smtp_server,
                config['port'],
                smtp_user,
                smtp_password,
                from_email,
                to_email,
                msg,
                config['client_hostname']
            )
            
            if success:
                return jsonify({
                    "success": "✅ SUCCESS",
                    "message": "Email sent successfully with alternative configuration"
                }), 200

        return jsonify({
            "error": "❌ FAILURE",
            "message": f"Failed to send email: {error}"
        }), 500

    except Exception as e:
        app.logger.error(f'Error processing request: {str(e)}', exc_info=True)
        return jsonify({
            "error": "❌ FAILURE",
            "message": "Internal server error"
        }), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 