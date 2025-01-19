from flask import jsonify, request
from core.emulator_manager import EmulatorManager
from core.errors import EmulatorError
import time

def register_routes(app,emulator):
    @app.route('/status', methods=['GET'])
    def get_status():
        return jsonify(emulator.status_dict)

    @app.route('/program/launch', methods=['POST'])
    def launch_program():
        config = request.json
        return jsonify(emulator.launch_program(config))

    @app.route('/program/curate', methods=['POST'])
    def curate_program():
        config = request.json
        return jsonify(emulator.curate_program(config))

    @app.route('/program/stop', methods=['POST'])
    def stop_program():
        force = request.json.get('force', False)
        return jsonify(emulator.stop_program(force))

    @app.route('/dev/mode', methods=['POST'])
    def set_monitor_mode():
        """Switch between real process monitoring and simulated state"""
        try:
            mode = request.json.get('mode', 'REAL')
            return jsonify(emulator.set_monitor_mode(mode))
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400

    @app.route('/dev/state', methods=['POST'])
    def set_state():
        """Manually set emulator state for testing"""
        try:
            running_param = request.json.get('running')
            # Handle both string and boolean inputs
            if isinstance(running_param, str):
                running = running_param.lower() == 'true'
            else:
                running = bool(running_param)

            demo = request.json.get('demo')
            return jsonify(emulator.set_simulated_state(running, demo))
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400

    @app.route('/dev/error', methods=['POST'])
    def simulate_error():
        """Simulate an error message over WebSocket"""
        try:
            code = request.json.get('code', 'EMULATOR_CRASH')
            message = request.json.get('message', 'Simulated emulator crash')
            details = request.json.get('details', {
                'exitCode': 1,
                'processId': 1234,
                'timestamp': time.time()
            })
            emulator._notify_error(EmulatorError(code, message, details))
            return jsonify({'status': 'success', 'message': 'Error simulated'})
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400