from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uvicorn
import threading
import rclpy
from rclpy.node import Node
# from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from geometry_msgs.msg import Point
from sensor_msgs.msg import Image
import time

# To run server manually:
# uvicorn web_api:app --host mcalec.dyn.wpi.edu --port 8000
# To test, run this on another computer:
# curl -X POST http://mcalec.dyn.wpi.edu:8000/send_command/ -H "Content-Type: application/json" -d '{"command": "test"}'
# Additional installations:
# pip install 'uvicorn[standard]' websockets wsproto asyncio opencv-python-headless cv-bridge

class ROS2BridgeNode(Node):
    def __init__(self):
        super().__init__('ros2_web_bridge')

        # Parameters
        self.declare_parameter('coord_topic_start','/coord/start')
        self.declare_parameter('coord_topic_goal','/coord/goal')
        self.declare_parameter('camera_image_topic','/camera/camera/color/image_raw')
        self.declare_parameter('host','mcalec.dyn.wpi.edu')
        self.declare_parameter('port',8000)

        # Publishers
        self.coord_start_publisher = self.create_publisher(Point,self.get_parameter('coord_topic_start').value,10)
        self.coord_goal_publisher = self.create_publisher(Point,self.get_parameter('coord_topic_goal').value,10)

        # Subscribers
        self.create_subscription(Image,self.get_parameter('camera_image_topic').value,self.image_callback,10)

        # WebSocket
        self.host = self.get_parameter('host').value
        self.port = self.get_parameter('port').value

        self.cv_bridge = CvBridge()
        self.image = b''  # Empty bytes as default
        self.get_logger().info("ROS2 Web Bridge initialized")


    def send_targets(self, start: Point, goal: Point):
        '''
        Sends 2D start and goal points to vision node for processing 
        '''
        self.coord_start_publisher.publish(start)
        self.coord_goal_publisher.publish(goal)
        # return {"status": "command sent", "command": command}

    def image_callback(self, msg: Image):
        img = self.cv_bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        quality = 90
        success, jpg_data = cv2.imencode('.jpg',img,[cv2.IMWRITE_JPEG_QUALITY,quality])
        if success:
            self.image = jpg_data.tobytes()
        else:
            self.get_logger().warning("Failed to encode image as JPEG")

class WebAPIServer:
    def __init__(self, ros_node: ROS2BridgeNode):
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
        
        @self.app.websocket("/ws/camera/")
        async def websocket_camera(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    if self.ros_node.image and len(self.ros_node.image) > 0:
                        await websocket.send_bytes(self.ros_node.image)
                    await asyncio.sleep(0.1) # camera runs at 15 FPS but on Pi can be slower
            except WebSocketDisconnect:
                self.ros_node.get_logger().info("Client Disconnected")
            except Exception as e:
                self.ros_node.get_logger().error(f"WebSocket Error: {e}")
            finally:
                await websocket.close()


        # @self.app.post("/api/game/")
        # async def send_command(command: dict):
        #     robot_command = command.get("command", "default_command")
        #     self.ros_node.get_logger().info(f"Received API command: {robot_command}")
        #     return self.ros_node.send_command(robot_command)
            
        @self.app.websocket("/ws/game/{session_id}/")
        async def websocket_game(websocket: WebSocket, session_id: str):
            await websocket.accept()
            self.active_connections[session_id] = websocket
            try:
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    # if data["command"] == "detect_piece":
                    #     piece = self.detect_piece(data["x"], data["y"])
                    #     response = {
                    #         "type": "piece_detected",
                    #         "piece": piece
                    #     }
                    #     await websocket.send_text(json.dumps(response))
                    if data["command"] == "move_piece":
                        self.ros_node.get_logger().info(f"Move piece data: {data}")
                        success = self.move_piece(data["start_x"], data["start_y"], data["goal_x"], data["goal_y"])
                        response = {
                            "type": "move_response",
                            "success": success
                        }
                        await websocket.send_text(json.dumps(response))
                    else:
                        print(data)
            except WebSocketDisconnect:
                self.ros_node.get_logger().info(f"Disconnected session {session_id}")
                if session_id in self.active_connections:
                    del self.active_connections[session_id]
    
    # Mock piece detection function
    # def detect_piece(self, x, y):
    #     return {"id": "piece_1", "type": "pawn", "x": x, "y": y}

    # Mock piece movement function
    def move_piece(self, start_x, start_y, goal_x, goal_y):
        start = Point(x=float(start_x),y=float(start_y),z=0.)
        goal = Point(x=float(goal_x),y=float(goal_y),z=0.)
        self.ros_node.get_logger().info(f"Moving piece from ({start.x},{start.y}) to ({goal.x},{goal.y})")
        # TODO consider making a service that takes both and pends moving
        self.ros_node.coord_start_publisher.publish(start)
        self.ros_node.coord_goal_publisher.publish(goal)
        time.sleep(0.5)
        return True  # Simulate success
    
    def run(self, host="mcalec.dyn.wpi.edu", port=8000):
        host = self.ros_node.host if not None else host
        port = self.ros_node.port if not None else port
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