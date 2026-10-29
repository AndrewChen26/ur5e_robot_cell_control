from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile
from launch_ros.substitutions import FindPackageShare

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    TextSubstitution,
)


def generate_launch_description():
    ur_type = LaunchConfiguration("ur_type")
    robot_ip = LaunchConfiguration("robot_ip")
    controllers_file = LaunchConfiguration("controllers_file")
    namespace = LaunchConfiguration("namespace")
    tf_prefix = LaunchConfiguration("tf_prefix")
    initial_joint_controller = LaunchConfiguration("initial_joint_controller")
    use_mock_hardware = LaunchConfiguration("use_mock_hardware")
    reverse_port = LaunchConfiguration("reverse_port")
    script_sender_port = LaunchConfiguration("script_sender_port")
    script_command_port = LaunchConfiguration("script_command_port")
    trajectory_port = LaunchConfiguration("trajectory_port")
    tool_tcp_port = LaunchConfiguration("tool_tcp_port")
    use_gripper = LaunchConfiguration("use_gripper")
    description_file = LaunchConfiguration("description_file")
    com_port = LaunchConfiguration("com_port")
    use_tool_communication = LaunchConfiguration("use_tool_communication")
    tool_device_name = LaunchConfiguration("tool_device_name")
    tool_voltage = LaunchConfiguration("tool_voltage")
    declared_arguments = []
    declared_arguments.append(
        DeclareLaunchArgument(
            "ur_type",
            description="Type/series of used UR robot.",
            choices=[
                "ur3",
                "ur3e",
                "ur5",
                "ur5e",
                "ur10",
                "ur10e",
                "ur16e",
                "ur20",
                "ur30",
            ],
            default_value="ur5e",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "robot_ip",
            description="IP address by which the robot can be reached.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "namespace",
            default_value="",
            description="ROS namespace to push this robot's nodes under. Set this "
            "(and a distinct tf_prefix) when launching more than one robot at once, "
            "e.g. 'leader' / 'follower', so the two instances don't collide.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tf_prefix",
            default_value=[namespace, "_"],
            description="tf_prefix of the joint names. Defaults to '<namespace>_' so "
            "two robots of the same ur_type still get distinct link/joint names; "
            "override explicitly if needed.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument("launch_rviz", default_value="true", description="Launch RViz?")
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "initial_joint_controller",
            default_value="scaled_joint_trajectory_controller",
            description="Initially activated & loaded controller, e.g. "
            "'freedrive_mode_controller' for a hand-guided leader arm or "
            "'forward_position_controller' for a arm driven by streamed position commands.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_mock_hardware",
            default_value="false",
            description="Start robot with mock hardware mirroring commanded state, no "
            "physical robot required.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "controllers_file",
            default_value=PathJoinSubstitution([
                FindPackageShare("ur5e_robot_cell_control"),
                "config",
                "ros2_controllers.yaml",
            ]),
            description="Path to ros2_control controllers YAML.")
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_gripper",
            default_value="false",
            description="Also spawn the Robotiq gripper controllers "
            "(robotiq_gripper_controller / robotiq_activation_controller). Requires "
            "description_file to actually export the Robotiq ros2_control hardware "
            "interface - the default arm-only description_file does not; pass "
            "ur5e_gripper_controlled.urdf.xacro (see its description_file argument) "
            "alongside this.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_file",
            default_value=PathJoinSubstitution(
                [FindPackageShare("ur_robot_driver"), "urdf", "ur.urdf.xacro"]
            ),
            description="URDF/XACRO description file (absolute path). Default is the "
            "arm-only description shipped with ur_robot_driver; pass "
            "ur5e_robot_cell_control/urdf/ur5e_gripper_controlled.urdf.xacro (with "
            "use_gripper:=true) to also bring up a Robotiq gripper.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "com_port",
            default_value="/dev/ttyUSB0",
            description="Serial device a Robotiq gripper is bridged on. Only meaningful "
            "when description_file declares this xacro arg (e.g. "
            "ur5e_gripper_controlled.urdf.xacro); harmlessly ignored otherwise. Must be "
            "distinct per robot cell if running two on one host, same as the reverse/"
            "script/trajectory ports below.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_tool_communication",
            default_value="false",
            description="Bridge this robot's internal RS-485 tool port to a local pty "
            "(tool_device_name) via ur_robot_driver's tool_communication_node. This is "
            "how tcp_controller.launch.py's proven single-arm+gripper setup connects its "
            "Robotiq gripper - set this true alongside use_gripper:=true and com_port == "
            "tool_device_name if this robot's gripper is wired the same way (as opposed "
            "to a plain external USB-to-serial adapter, which needs neither).",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_device_name",
            default_value="/tmp/ttyUR",
            description="Local pty tool_communication_node bridges this robot's tool "
            "port to. Only meaningful with use_tool_communication:=true - and then it "
            "must match com_port exactly, since that's the device the gripper driver "
            "actually opens. Must be distinct per robot cell running on the same host "
            "at the same time.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_voltage",
            default_value="0",
            description="Voltage supplied on the robot's tool connector. 0 is a "
            "conservative default that won't power anything; a Robotiq gripper wired "
            "through the tool port (use_tool_communication:=true) needs this set to "
            "24 or it gets no power at all and never responds - confirmed on real "
            "hardware (every Modbus command reads back 0 bytes until this is set). "
            "tcp_controller.launch.py's proven single-arm+gripper setup defaults to 24.",
        )
    )
    # These are local (PC-side) TCP ports the driver listens on for the robot to connect
    # back to - they default to the same values as ur_robot_driver's own launch file,
    # which is fine for one robot. Running a second robot's driver on the same machine
    # (e.g. leader + follower) requires giving it distinct ports, or the second driver's
    # sockets fail to bind ("Address already in use") since these are per-*host*, not
    # per-robot-IP. dual_arm_teleop.launch.py overrides these for the follower.
    declared_arguments.append(
        DeclareLaunchArgument(
            "reverse_port",
            default_value="50001",
            description="Port used to send cyclic instructions from the driver to the "
            "robot controller. Must be unique per robot driver running on this host.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "script_sender_port",
            default_value="50002",
            description="Port the driver offers to query the external_control URScript "
            "on. Must be unique per robot driver running on this host.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "trajectory_port",
            default_value="50003",
            description="Port opened for trajectory control. Must be unique per robot "
            "driver running on this host.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "script_command_port",
            default_value="50004",
            description="Port used to forward URScript commands to the robot. Must be "
            "unique per robot driver running on this host.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_tcp_port",
            default_value="54321",
            description="Local port used for bridging the tool's serial device (only "
            "relevant if use_tool_communication is true). Must be unique per robot "
            "driver running on this host.",
        )
    )
    return LaunchDescription(
        declared_arguments
        + [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    [
                        PathJoinSubstitution(
                            [
                                FindPackageShare("ur5e_robot_cell_control"),
                                "launch",
                                "ur_gripper_control.launch.py",
                            ]
                        )
                    ]
                ),
                launch_arguments={
                    "ur_type": ur_type,
                    "robot_ip": robot_ip,
                    "namespace": namespace,
                    "tf_prefix": tf_prefix,
                    "initial_joint_controller": initial_joint_controller,
                    "use_mock_hardware": use_mock_hardware,
                    "launch_rviz": LaunchConfiguration("launch_rviz"),
                    "rviz_config_file": PathJoinSubstitution(
                        [
                            FindPackageShare("ur5e_robot_cell_description"),
                            "rviz",
                            "view_robot.rviz",
                        ]
                    ),
                    "description_launchfile": PathJoinSubstitution(
                        [
                            FindPackageShare("ur5e_robot_cell_control"),
                            "launch",
                            "rsp.launch.py",
                        ]
                    ),
                    "controllers_file": controllers_file,
                    "reverse_port": reverse_port,
                    "script_sender_port": script_sender_port,
                    "script_command_port": script_command_port,
                    "trajectory_port": trajectory_port,
                    "tool_tcp_port": tool_tcp_port,
                    "use_gripper": use_gripper,
                    "description_file": description_file,
                    "com_port": com_port,
                    "use_tool_communication": use_tool_communication,
                    "tool_device_name": tool_device_name,
                    "tool_voltage": tool_voltage,
                }.items(),
            ),
        ]
    )
