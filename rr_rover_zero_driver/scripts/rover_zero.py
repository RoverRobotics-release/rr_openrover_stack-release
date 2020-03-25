#!/usr/bin/env python
from roboclaw_driver.roboclaw import Roboclaw
import rospy
from geometry_msgs.msg import Twist
from threading import Lock
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus

class RoverZeroNode:
    def __init__(self):
        self._node = rospy.init_node('Rover_Zero_Controller', anonymous=True)

        # Class Variables
        self._left_effort = 64
        self._right_effort = 64
        self._safety_lock = Lock()

        # Diagnostic Parameters
        self._firmware_version = None
        self._left_motor_current = None
        self._right_motor_current = None
        self._battery_voltage = None

        # ROS params
        self._port = rospy.get_param('~dev', '/dev/ttyACM0')
        self._address = rospy.get_param('~address', 0x80)
        self._baud = rospy.get_param('~baud', 115200)
        self._timeout = rospy.get_param('~timeout', 0.1)
        self._attempts = rospy.get_param('~attempts', 1)
        self._max_vel = rospy.get_param('~max_vel', 5.0)
        self._effort_coef = rospy.get_param('~effort_coef', 0.09)
        self._max_turn = rospy.get_param('~max_turn', 6.28)
        self._turn_coeff = rospy.get_param('~turn_coefficient', 1.5)
        self._linear_coeff = rospy.get_param('~linear_coefficient', 3.0)
        self._diag_frequency = rospy.get_param('~diag_frequency', 1.0)
        self._wheel_base = 0.358775  # Distance between center of wheels
        self._wheel_radius = 0.127   # Radius of wheel

        # ROS Publishers
        self._pub_diag = rospy.Publisher('/diagnostics', DiagnosticArray, queue_size=1)

        # ROS Subscribers
        self._twist_sub = rospy.Subscriber("/cmd_vel", Twist, self._twist_cb, queue_size=1)

        # ROS Timers
        rospy.Timer(rospy.Duration(self._diag_frequency), self._diag_cb)

        # Initialize Roboclaw Serial
        self._roboclaw = Roboclaw(self._port, self._baud)
        if not self._roboclaw.Open():
            rospy.logfatal('Could not open serial at ' + self._port)

        # Get Roboclaw Firmware Version
        self._firmware_version =self._roboclaw.ReadVersion(self._address)

    def get_battery_voltage(self):
        self._battery_voltage = self._roboclaw.ReadMainBatteryVoltage(self._address)

    def get_motor_current(self):
        (res, m1_current, m2_current) = self._roboclaw.ReadCurrents(self._address)
        if res:
            self._left_motor_current = m1_current
            self._right_motor_current = m2_current

    def set_effort(self, left_effort, right_effort):
        self._roboclaw.ForwardBackwardM1(self._address, left_effort)
        self._roboclaw.ForwardBackwardM2(self._address, right_effort)

    def spin(self):
        rospy.spin()

    def _twist_cb(self, cmd):
        self._left_effort, self._right_effort = self._twist_to_esc_effort(cmd.linear.x, cmd.angular.z)
        self._safety_lock.acquire()
        self.set_effort(self._left_effort, self._right_effort)
        self._safety_lock.release()

    def _twist_to_esc_effort(self, linear_rate, angular_rate):
        if linear_rate > self._max_vel:
            linear_rate = self._max_vel
        if angular_rate > self._max_turn:
            angular_rate = self._max_turn

        left_ = (linear_rate - 0.5 * self._wheel_base * angular_rate) / self._wheel_radius
        right_ = (linear_rate + 0.5 * self._wheel_base * angular_rate) / self._wheel_radius

        return (self.speed_to_effort(left_), self.speed_to_effort(right_))

    def speed_to_effort(self, speed):
        if abs(speed) > self._max_vel:
            speed = self._max_vel if speed >= 0 else -self._max_vel
        effort = int(63 * (self._effort_coef * speed)) + 64
        if effort < 0:
            effort = 0
        if effort > 127:
            effort = 127
        return effort

    def _diagnostics(self):
        self.get_battery_voltage()
        self.get_motor_current()

    def _diag_cb(self, event):
        # rospy is not thread safe.  This prevents serial interference
        self._safety_lock.acquire()
        self._diagnostics()
        self._safety_lock.release()
        darr = DiagnosticArray()
        darr.status = [
            DiagnosticStatus(name='Firmware Version', message=self._firmware_version),
            DiagnosticStatus(name='Left Motor Current', message=''),
            DiagnosticStatus(name='Right Motor Current', message=''),
            DiagnosticStatus(name='Battery Voltage', message='{VOLTAGE}V'.format(VOLTAGE=str(self._battery_voltage)))
        ]
        self._pub_diag.publish(darr)


if __name__ == '__main__':
    rz = RoverZeroNode()
    rz.spin()
