from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uvicorn
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class ROS2BridgeNode(Node):
    def __init__(self):
        super().__init__('ros2_web_bridge')
        self.publisher = self.create_publisher(String, '/game_command', 10)
        self.get_logger().info("ROS2 Web Bridge initialized")

    def send_command(self, command: str):
        msg = String()
        msg.data = command
        self.publisher.publish(msg)
        self.get_logger().info(f"Sent command to ROS2: {command}")
        return {"status": "command sent", "command": command}

class WebAPIServer:
    def __init__(self, ros_node):
        self.app = FastAPI()
        self.ros_node = ros_node
        self.active_connections = {}
        
        # CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register routes
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.websocket("/ws/status/")
        async def websocket_status(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_text()
                    self.ros_node.get_logger().info(f"Status received: {data}")
                    await websocket.send_text("Status acknowledged!")
            except WebSocketDisconnect:
                self.ros_node.get_logger().info("Client Disconnected")
            except Exception as e:
                self.ros_node.get_logger().error(f"WebSocket Error: {e}")
            finally:
                await websocket.close()
                
        @self.app.post("/api/game/")
        async def send_command(command: dict):
            robot_command = command.get("command", "default_command")
            self.ros_node.get_logger().info(f"Received API command: {robot_command}")
            return self.ros_node.send_command(robot_command)
            
        @self.app.websocket("/ws/game/{session_id}/")
        async def websocket_game(websocket: WebSocket, session_id: str):
            await websocket.accept()
            self.active_connections[session_id] = websocket
            try:
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    if data["command"] == "detect_piece":
                        piece = self.detect_piece(data["x"], data["y"])
                        response = {
                            "type": "piece_detected",
                            "piece": piece
                        }
                        await websocket.send_text(json.dumps(response))
                    elif data["command"] == "move_piece":
                        self.ros_node.get_logger().info(f"Move piece data: {data}")
                        success = self.move_piece(data["piece_id"], data["target_x"], data["target_y"])
                        response = {
                            "type": "move_response",
                            "success": success
                        }
                        await websocket.send_text(json.dumps(response))
            except WebSocketDisconnect:
                self.ros_node.get_logger().info(f"Disconnected session {session_id}")
                if session_id in self.active_connections:
                    del self.active_connections[session_id]
    
    # Mock piece detection function
    def detect_piece(self, x, y):
        return {"id": "piece_1", "type": "pawn", "x": x, "y": y}

    # Mock piece movement function
    def move_piece(self, piece_id, x, y):
        self.ros_node.get_logger().info(f"Moving piece {piece_id} to {x}, {y}")
        return True  # Simulate success
    
    def run(self, host="mcalec.dyn.wpi.edu", port=8000):
        uvicorn.run(self.app, host=host, port=port)

def main(args=None):
    rclpy.init(args=args)
    node = ROS2BridgeNode()
    
    # Create and run the web server in a separate thread
    api_server = WebAPIServer(node)
    server_thread = threading.Thread(target=api_server.run, daemon=True)
    server_thread.start()
    
    try:
        # Run the ROS2 node in the main thread
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Node stopped cleanly")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()