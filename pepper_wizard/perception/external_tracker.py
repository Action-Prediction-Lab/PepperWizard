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
           # We don't strictly need registerTarget for lookAt, but it's good practice to clear.
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
        
        # [DEADZONE Check] - Independent Axes
        # If BOTH are within their respective deadzones, do nothing.
        # If EITHER is outside, we proceed (typically we want to correct both if we move at all)
        # OR should we zero out the one that is inside? 
        # Usually for natural movement, if we move, we move both. But if valid 'ignore' zone, we ignore.
        if abs(yaw) < deadzone_yaw and abs(pitch) < deadzone_pitch:
            # We are close enough in BOTH axes.
            return
        
        # 3. Project to 3D Point (Robot Frame approx)
        # We assume the camera is at (0,0,0) relative to the look target for this calculation,
        # but ALTracker expects coordinates in FRAME_ROBOT (or TORSO).
        # However, lookAt takes a point.
        # If we provide a point relative to the FRAME_ROBOT, we need to know the head's current position to project accurately.
        # BUT, simpler approximation:
        # X = Forward = distance
        # Y = Left = distance * tan(yaw)
        # Z = Up = distance * tan(pitch)
        
        # Wait, ALTracker lookAt in FRAME_ROBOT means [X, Y, Z] relative to the robot's feet (roughly).
        # If we send [1.5, 0, 0], it looks straight forward at chest height.
        # If we want to look at a face, Z should be high (~1.2m - 1.6m).
        
        # If we use FRAME_TORSO (0), (0,0,0) is the chest.
        # Let's use FRAME_ROBOT (2).
        # We need to add the Head's height to Z?
        # Actually, let's use a "relative" approach logic or just assume a standard head height.
        
        # Better: Calculate "Offset" from "Straight Ahead".
        x = self.target_distance
        y = self.target_distance * math.tan(yaw)
        z_offset = self.target_distance * math.tan(pitch)
        
        # Robot Head Height is approx 1.2m.
        # But wait, lookAt target is absolute.
        # If we interpret the camera image as "offsets from where I am looking now", we create a positive feedback loop error.
        # If we interpret it as "offsets from straight ahead", that assumes the head is centered.
        
        # CRITICAL: We only have 2D info. We don't know "where I am looking now" without querying sensors.
        # The standard approach without re-querying angles constantly is:
        # 1. Get current HeadYaw/Pitch (Sensor).
        # 2. Add pixel-offset angles.
        # 3. Project that absolute direction to a point.
        
        try:
            curr_yaw, curr_pitch = 0.0, 0.0

            if reference_angles:
                 # Use the exact angles from when the image was taken
                 curr_yaw, curr_pitch = reference_angles
            else:
                 # If no reference provided, we cannot accurately compensate for ego-motion without duplicating 
                 # the proprioception service's role. We will assume 0 or raise warning.
                 # User requested no duplication.
                 # We'll default to 0.0 (relative movement only) or just return if critical.
                 print("ExternalTracker Warning: No reference angles provided. Tracking may overshoot.")
                 return
            
            # Add relative offsets
            # Image Right (cx > 0.5) -> Negative Yaw (Right)
            # Image Left (cx < 0.5) -> Positive Yaw (Left)
            # Our off_x = 0.5 - cx.
            # If cx = 1.0 (Right edge), off_x = -0.5. Yaw angle = -0.5 * FOV. Correct.
            
            target_yaw = curr_yaw + yaw
            target_pitch = curr_pitch + pitch
            
            # Now project to 3D point in Robot Frame
            # X = r * cos(pitch) * cos(yaw)
            # Y = r * cos(pitch) * sin(yaw)
            # Z = r * sin(pitch) + HeadHeight
            
            # Head Height ~ 1.25m
            head_z = 1.25
            
            x_pos = self.target_distance * math.cos(target_pitch) * math.cos(target_yaw)
            y_pos = self.target_distance * math.cos(target_pitch) * math.sin(target_yaw)
            z_pos = (self.target_distance * math.sin(-target_pitch)) + head_z 
            # Note: Pitch is inverse in Naoqi? Down is positive?
            # Standard Naoqi: HeadPitch Positive = Down.
            # Our pitch calc: off_y = 0.5 - cy.
            # If cy = 1.0 (Bottom), off_y = -0.5. Angle = Negative.
            # So Image Bottom = Negative Pitch.
            # But Naoqi Down = Positive Pitch.
            # So we need to invert our pitch delta.
            pitch_delta = -(off_y * self.vfov_rad)
            target_pitch = curr_pitch + pitch_delta
            
            # Recalculate Z with verified pitch sign
            z_pos = (self.target_distance * math.sin(-target_pitch)) + head_z
            # If pitch is +0.5 (Down), sin(-0.5) is negative. Z decreases. Correct.
            
            point = [x_pos, y_pos, z_pos]
            
            # Send to ALTracker
            # Mode: Head (we use whole body = False usually to avoid feet moving)
            # Use whole body = False
            # [OPTIMIZATION] Use 'post' to make it non-blocking! 
            # This allows us to send updates at 15Hz without waiting for the head to reach the target.
            self.robot_client.client.ALTracker.post("lookAt", point, self.frame_robot, fraction_speed, False)
            
        except Exception as e:
            print(f"ExternalTracker Error: {e}")

    def stop(self):
        try:
            self.robot_client.client.ALTracker.stopTracker()
        except:
            pass
