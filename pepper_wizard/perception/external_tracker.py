import numpy as np
import time
import math
from ..robot_client import RobotClient

class ExternalTracker:
    """
    Manages head tracking by sending 3D coordinates to Naoqi's ALTracker.lookAt.
    Projects 2D image coordinates to a fixed-depth 3D plane.
    """
    def __init__(self, robot_client, target_distance=1.5):
        """
        Args:
            robot_client: Instance of RobotClient (wrapper for Naoqi).
            target_distance: Distance in meters to project the target (default 1.5m).
        """
        self.robot_client = robot_client
        self.target_distance = target_distance
        
        # Camera Intrinsics (Approximate for Pepper Top Camera)
        # HFOV ~57 deg, VFOV ~44 deg
        self.hfov_rad = 57.0 * (math.pi / 180.0)
        self.vfov_rad = 44.0 * (math.pi / 180.0)
        
        self.running = False
        self.frame_robot = 2 # FRAME_ROBOT
        
        # Ensure tracker is ready
        try:
           self.robot_client.client.ALTracker.stopTracker()
           self.robot_client.client.ALTracker.unregisterAllTargets()
           # It is not strictly necessary to registerTarget for lookAt, but it's good practice to clear.
        except Exception as e:
            print(f"ExternalTracker Init Warning: {e}")

    def look_at(self, bbox_norm, fraction_speed=0.2, reference_angles=None, deadzone_yaw=0.04, deadzone_pitch=0.15):
        """
        Commands the robot to look at the center of the bounding box.
        
        Args:
            bbox_norm: [x1, y1, x2, y2] normalized (0.0 to 1.0).
            fraction_speed: Speed fraction (0.0 to 1.0).
            reference_angles: Optional [yaw, pitch] at the time of image capture.
            deadzone_yaw: Yaw threshold in radians (default 0.04 ~ 2.3 deg).
            deadzone_pitch: Pitch threshold in radians (default 0.15 ~ 8.5 deg).
        """
        # 1. Calculate Center (Normalized)
        cx = (bbox_norm[0] + bbox_norm[2]) / 2.0
        cy = (bbox_norm[1] + bbox_norm[3]) / 2.0
        
        # 2. Convert to Camera Frame Coordinates (Angles)
        # 0.5 is center. <0.5 is left/up, >0.5 is right/down.
        # Pepper Camera: X is forward, Y is Left, Z is Up.
        
        # Calculate offset from center (-0.5 to 0.5)
        off_x = 0.5 - cx # +Left, -Right
        off_y = 0.5 - cy # +Up, -Down
        
        # Convert to angles
        yaw = off_x * self.hfov_rad
        pitch = off_y * self.vfov_rad
        
        # 3. Deadzone Filter (Independent Axes)
        # Movement is suppressed only if the target is within tolerance for BOTH axes.
        if abs(yaw) < deadzone_yaw and abs(pitch) < deadzone_pitch:
            return
        
        # 3. Project to 3D Point (Robot Frame approx)
        x = self.target_distance
        y = self.target_distance * math.tan(yaw)
        z_offset = self.target_distance * math.tan(pitch)
        
        
        try:
            curr_yaw, curr_pitch = 0.0, 0.0

            if reference_angles:
                 # Use the exact angles from when the image was taken
                 curr_yaw, curr_pitch = reference_angles
            else:
                 print("ExternalTracker Warning: No reference angles provided. Tracking may overshoot.")
                 return
                        
            target_yaw = curr_yaw + yaw
            target_pitch = curr_pitch + pitch
            
            # Project to 3D point in Robot Frame
            # X = r * cos(pitch) * cos(yaw)
            # Y = r * cos(pitch) * sin(yaw)
            # Z = r * sin(pitch) + HeadHeight
            
            # Head Height ~ 1.21m
            head_z = 1.21
            
            x_pos = self.target_distance * math.cos(target_pitch) * math.cos(target_yaw)
            y_pos = self.target_distance * math.cos(target_pitch) * math.sin(target_yaw)
            z_pos = (self.target_distance * math.sin(-target_pitch)) + head_z 
            # Standard Naoqi: HeadPitch Positive = Down.
            pitch_delta = -(off_y * self.vfov_rad)
            target_pitch = curr_pitch + pitch_delta
            
            # Recalculate Z with verified pitch sign
            z_pos = (self.target_distance * math.sin(-target_pitch)) + head_z
            
            point = [x_pos, y_pos, z_pos]
            
            # Send to ALTracker
            self.robot_client.client.ALTracker.post("lookAt", point, self.frame_robot, fraction_speed, False)
            
        except Exception as e:
            print(f"ExternalTracker Error: {e}")

    def stop(self):
        try:
            self.robot_client.client.ALTracker.stopTracker()
        except:
            pass
