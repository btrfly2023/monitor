# web_log_server.py without password protection and using relative log path

from flask import Flask, render_template_string, request, Response
import os
import time
import threading
import logging

app = Flask(__name__)

# Configuration with relative path
LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../logs/blockchain_monitor.log")
REFRESH_INTERVAL = 30  # Auto-refresh interval in seconds
MAX_LINES = 200  # Maximum number of lines to display

# HTML template for the log viewer (simplified without login form)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Blockchain Monitor Logs</title>
    <meta http-equiv="refresh" content="{{ refresh_interval }}" />
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: monospace;
            background-color: #1e1e1e;
            color: #dcdcdc;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #444;
        }
        .log-container {
            background-color: #252526;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .controls {
            margin-bottom: 15px;
        }
        .refresh-info {
            font-size: 0.8em;
            color: #888;
        }
        .error { color: #ff6b6b; }
        .warning { color: #feca57; }
        .info { color: #1dd1a1; }
        .debug { color: #54a0ff; }
        .timestamp { color: #c8d6e5; }
        input, button, select {
            padding: 8px;
            margin: 5px 5px 5px 0;
        }
        button {
            background-color: #0366d6;
            color: white;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background-color: #0255b3;
        }
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 5px;
        }
        .status-running {
            background-color: #1dd1a1;
        }
        .status-error {
            background-color: #ff6b6b;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Blockchain Monitor Logs</h1>
            <div>
                <span class="status-indicator {{ 'status-running' if is_running else 'status-error' }}"></span>
                Status: {{ "Running" if is_running else "Not Running" }}
            </div>
        </div>
        
        <div class="controls">
            <form method="get">
                <label for="lines">Lines to show:</label>
                <select name="lines" id="lines" onchange="this.form.submit()">
                    <option value="100" {% if lines == 100 %}selected{% endif %}>100</option>
                    <option value="250" {% if lines == 250 %}selected{% endif %}>250</option>
                    <option value="500" {% if lines == 500 %}selected{% endif %}>500</option>
                    <option value="1000" {% if lines == 1000 %}selected{% endif %}>1000</option>
                </select>
                
                <label for="refresh">Auto-refresh:</label>
                <select name="refresh" id="refresh" onchange="this.form.submit()">
                    <option value="10" {% if refresh_interval == 10 %}selected{% endif %}>10s</option>
                    <option value="30" {% if refresh_interval == 30 %}selected{% endif %}>30s</option>
                    <option value="60" {% if refresh_interval == 60 %}selected{% endif %}>1m</option>
                    <option value="300" {% if refresh_interval == 300 %}selected{% endif %}>5m</option>
                    <option value="0" {% if refresh_interval == 0 %}selected{% endif %}>Off</option>
                </select>
                
                <button type="submit" name="action" value="refresh">Refresh Now</button>
                <button type="submit" name="action" value="download">Download Full Log</button>
            </form>
            <p class="refresh-info">Last updated: {{ last_updated }} {% if refresh_interval > 0 %}(Auto-refresh: {{ refresh_interval }}s){% endif %}</p>
        </div>
        
        <div class="log-container">
{{ log_content }}
        </div>
    </div>
</body>
</html>
"""

def tail_file(file_path, lines=100):
    """Read the last n lines of a file"""
    try:
        if not os.path.exists(file_path):
            return f"Log file not found: {file_path}"
            
        with open(file_path, 'r') as f:
            # Read all lines and get the last 'lines' number of them
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading log file: {str(e)}"

def is_process_running():
    """Check if the blockchain monitor process is running"""
    try:
        # This is a simple check - you might need to adapt it to your specific setup
        with open(LOG_FILE_PATH, 'r') as f:
            last_lines = ''.join(f.readlines()[-20:])  # Check last 20 lines
            # If there's a log entry in the last 30 minutes, consider it running
            import re
            from datetime import datetime, timedelta
            
            # Extract timestamps from log lines
            timestamps = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_lines)
            if timestamps:
                last_timestamp = datetime.strptime(timestamps[-1], '%Y-%m-%d %H:%M:%S')
                now = datetime.now()
                return (now - last_timestamp) < timedelta(minutes=30)
        return False
    except Exception:
        return False

def colorize_log(log_content):
    """Add HTML color formatting to log lines based on log level"""
    import re
    
    # Define regex patterns for different log levels
    patterns = {
        'ERROR': r'^(.*?ERROR.*?)$',
        'WARNING': r'^(.*?WARNING.*?)$',
        'INFO': r'^(.*?INFO.*?)$',
        'DEBUG': r'^(.*?DEBUG.*?)$'
    }
    
    # Apply timestamp coloring first
    log_content = re.sub(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
        r'<span class="timestamp">\1</span>',
        log_content,
        flags=re.MULTILINE
    )
    
    # Apply log level coloring
    for level, pattern in patterns.items():
        css_class = level.lower()
        log_content = re.sub(
            pattern,
            r'<span class="' + css_class + r'">\1</span>',
            log_content,
            flags=re.MULTILINE
        )
    
    return log_content

@app.route('/', methods=['GET'])
def index():
    # Handle download request
    if request.args.get('action') == 'download':
        try:
            return Response(
                open(LOG_FILE_PATH, 'r').read(),
                mimetype='text/plain',
                headers={"Content-Disposition": f"attachment;filename=blockchain_monitor_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"}
            )
        except Exception as e:
            return f"Error downloading log file: {str(e)}"
    
    # Get parameters
    lines = min(int(request.args.get('lines', MAX_LINES)), 2000)  # Limit to 2000 lines max
    refresh_interval = int(request.args.get('refresh', REFRESH_INTERVAL))
    
    # Get log content
    log_content = tail_file(LOG_FILE_PATH, lines)
    
    # Colorize log content
    colored_log = colorize_log(log_content)
    
    return render_template_string(
        HTML_TEMPLATE, 
        log_content=colored_log,
        refresh_interval=refresh_interval,
        lines=lines,
        last_updated=time.strftime("%Y-%m-%d %H:%M:%S"),
        is_running=is_process_running()
    )

def start_web_server(host='0.0.0.0', port=8080):
    """Start the web server in a separate thread"""
    def run_server():
        app.run(host=host, port=port, debug=False, use_reloader=False)
    
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logging.info(f"Web log server started at http://{host}:{port}")
    logging.info(f"Monitoring log file: {LOG_FILE_PATH}")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Start the web server
    start_web_server()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Web server stopped")
