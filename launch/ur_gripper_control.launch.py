# Copyright (c) 2021 PickNik, Inc.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
#    * Neither the name of the {copyright_holder} nor the names of its
#      contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

#
# Author: Denis Stogl

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import (
    AndSubstitution,
    LaunchConfiguration,
    NotSubstitution,
    PathJoinSubstitution,
)
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.parameter_descriptions import ParameterFile
from launch_ros.substitutions import FindPackageShare


def launch_setup(context):
    # Initialize Arguments
    ur_type = LaunchConfiguration("ur_type")
    robot_ip = LaunchConfiguration("robot_ip")
    namespace = LaunchConfiguration("namespace")
    use_gripper = LaunchConfiguration("use_gripper")
    # Namespace is resolved up front (rather than kept as a substitution) so it can be
    # spliced into the controller_stopper/spawner CLI args below, which PushRosNamespace
    # does not rewrite since they're plain strings, not ROS names.
    namespace_value = namespace.perform(context)
    controller_manager_name = (
        f"/{namespace_value}/controller_manager" if namespace_value else "/controller_manager"
    )
    # General arguments
    controllers_file = LaunchConfiguration("controllers_file")
    description_launchfile = LaunchConfiguration("description_launchfile")
    use_mock_hardware = LaunchConfiguration("use_mock_hardware")
    controller_spawner_timeout = LaunchConfiguration("controller_spawner_timeout")
    description_file = LaunchConfiguration("description_file")
    com_port = LaunchConfiguration("com_port")
    initial_joint_controller = LaunchConfiguration("initial_joint_controller")
    activate_joint_controller = LaunchConfiguration("activate_joint_controller")
    launch_rviz = LaunchConfiguration("launch_rviz")
    rviz_config_file = LaunchConfiguration("rviz_config_file")
    headless_mode = LaunchConfiguration("headless_mode")
    launch_dashboard_client = LaunchConfiguration("launch_dashboard_client")
    use_tool_communication = LaunchConfiguration("use_tool_communication")
    tool_device_name = LaunchConfiguration("tool_device_name")
    tool_tcp_port = LaunchConfiguration("tool_tcp_port")
    tool_voltage = LaunchConfiguration("tool_voltage")

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            LaunchConfiguration("update_rate_config_file"),
            ParameterFile(controllers_file, allow_substs=True),
            # We use the tf_prefix as substitution in there, so that's why we keep it as an
            # argument for this launchfile
        ],
        output="screen",
    )


    dashboard_client_node = Node(
        package="ur_robot_driver",
        condition=IfCondition(
            AndSubstitution(launch_dashboard_client, NotSubstitution(use_mock_hardware))
        ),
        executable="dashboard_client",
        name="dashboard_client",
        output="screen",
        emulate_tty=True,
        parameters=[{"robot_ip": robot_ip}],
    )

    robot_state_helper_node = Node(
        package="ur_robot_driver",
        executable="robot_state_helper",
        name="ur_robot_state_helper",
        output="screen",
        condition=UnlessCondition(use_mock_hardware),
        parameters=[
            {"headless_mode": headless_mode},
            {"robot_ip": robot_ip},
        ],
    )

    tool_communication_node = Node(
        package="ur_robot_driver",
        condition=IfCondition(use_tool_communication),
        executable="tool_communication.py",
        name="ur_tool_comm",
        output="screen",
        parameters=[
            {
                "robot_ip": robot_ip,
                "tcp_port": tool_tcp_port,
                "device_name": tool_device_name,
            }
        ],
    )

    urscript_interface = Node(
        package="ur_robot_driver",
        executable="urscript_interface",
        parameters=[{"robot_ip": robot_ip}],
        output="screen",
        condition=UnlessCondition(use_mock_hardware),
    )

    # Controllers controller_stopper_node never touches, regardless of whether it sees
    # the robot's "External Control" program as running - everything else it activates/
    # deactivates in lockstep with that. robotiq_gripper_controller belongs here too when
    # a gripper is in play: unlike arm motion controllers, there's no "stale queued
    # motion after E-stop/pause" risk for it (the gripper's own activation state is
    # separate, Modbus-driven, not URScript-driven) - and leaving it off this list is a
    # real bug, not just a missed optimization: confirmed on real hardware that a single
    # brief robot_program_running blip early in startup can deactivate it and never
    # reactivate it, leaving the gripper silently unresponsive to every command with no
    # error anywhere. tcp_controller.launch.py's own proven single-arm+gripper setup
    # already includes robotiq_gripper_controller here for exactly this reason.
    consistent_controllers = [
        "io_and_status_controller",
        "force_torque_sensor_broadcaster",
        "joint_state_broadcaster",
        "speed_scaling_state_broadcaster",
        "tcp_pose_broadcaster",
        "ur_configuration_controller",
    ]
    if use_gripper.perform(context) == "true":
        consistent_controllers.append("robotiq_gripper_controller")

    controller_stopper_node = Node(
        package="ur_robot_driver",
        executable="controller_stopper_node",
        name="controller_stopper",
        output="screen",
        emulate_tty=True,
        condition=UnlessCondition(use_mock_hardware),
        parameters=[
            {"headless_mode": headless_mode},
            {"joint_controller_active": activate_joint_controller},
            {"consistent_controllers": consistent_controllers},
        ],
    )

    # controller_manager_name is namespace-aware (see note above) since this is passed
    # verbatim to the spawner CLI, not resolved through ROS namespace remapping.

    rviz_node = Node(
        package="rviz2",
        condition=IfCondition(launch_rviz),
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", rviz_config_file],
    )

    # Spawn controllers
    def controller_spawner(controllers, active=True):
        inactive_flags = ["--inactive"] if not active else []
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[
                "--controller-manager",
                controller_manager_name,
                "--controller-manager-timeout",
                controller_spawner_timeout,
            ]
            + inactive_flags
            + controllers,
        )

    controllers_active = [
        "joint_state_broadcaster",
        "io_and_status_controller",
        "speed_scaling_state_broadcaster",
        "force_torque_sensor_broadcaster",
        "tcp_pose_broadcaster",
        "ur_configuration_controller",
    ]
    controllers_inactive = [
        "scaled_joint_trajectory_controller",
        "joint_trajectory_controller",
        "forward_velocity_controller",
        "forward_position_controller",
        "force_mode_controller",
        "passthrough_trajectory_controller",
        "freedrive_mode_controller",
        "tool_contact_controller",
    ]
    if use_gripper.perform(context) == "true":
        # These names must match ros2_controllers.yaml (robotiq_gripper_controller /
        # robotiq_activation_controller), and the URDF must actually export the Robotiq
        # ros2_control hardware interfaces (see ur5e_gripper_controlled.urdf.xacro) or
        # spawning these will fail.
        #
        # robotiq_gripper_controller (the GripperActionController exposing gripper_cmd)
        # goes active immediately - same split as tcp_controller.launch.py's already-
        # working single-arm+gripper setup. robotiq_activation_controller stays inactive:
        # it only exists to expose the reactivate_gripper recovery service, which
        # gripper_keyboard_teleop activates on demand rather than needing it running at
        # all times (confirmed by testing: leaving robotiq_gripper_controller in the
        # inactive list, as this used to, means gripper_cmd never comes up at all).
        controllers_active.append("robotiq_gripper_controller")
        controllers_inactive.append("robotiq_activation_controller")
    if activate_joint_controller.perform(context) == "true":
        controllers_active.append(initial_joint_controller.perform(context))
        controllers_inactive.remove(initial_joint_controller.perform(context))

    if use_mock_hardware.perform(context) == "true":
        controllers_active.remove("tcp_pose_broadcaster")

    controller_spawners = [
        controller_spawner(controllers_active),
        controller_spawner(controllers_inactive, active=False),
    ]

    rsp = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(description_launchfile),
        launch_arguments={
            "robot_ip": robot_ip,
            "ur_type": ur_type,
            # Forwarded explicitly (rather than relying on description_file/com_port
            # happening to already be set in the launch context by some ancestor) so
            # start_robot.launch.py's use_gripper path works regardless of where this
            # launch file is included from.
            "description_file": description_file,
            "com_port": com_port,
            # Also forwarded explicitly, for the same reason - this was previously
            # missing entirely, meaning rsp.launch.py always used its own conservative
            # default (0) no matter what this launch file's own tool_voltage argument
            # was set to. Confirmed on real hardware: with 0, a Robotiq gripper wired
            # through the tool port gets no power and every Modbus command it's sent
            # reads back 0 bytes - not a comms/timing problem, the gripper simply isn't
            # powered. tcp_controller.launch.py's proven single-arm+gripper setup runs
            # with this at 24.
            "tool_voltage": tool_voltage,
            # Forced "false", not left to fall through: "use_tool_communication" is also
            # this launch file's own argument (gating tool_communication_node below), and
            # LaunchConfiguration values leak across IncludeLaunchDescription boundaries
            # unless overridden explicitly (see start_robot.launch.py's use_gripper for
            # the same gotcha, found the hard way). The proven tcp_controller.launch.py
            # setup never sets this on the arm's own xacro at all - tool_communication_node
            # (a standalone bridge) is what actually owns the serial connection, not the
            # UR driver's own internal tool-comm handling - so this must always be false
            # here regardless of whatever this launch file's own use_tool_communication
            # (below) is set to.
            "use_tool_communication": "false",
        }.items(),
    )

    # With use_gripper + use_tool_communication, control_node's robotiq_driver hardware
    # plugin opens com_port (a pty) as part of its own startup - but tool_communication_node
    # is what creates that pty (and bridges it to the robot's tool port over TCP) in the
    # first place, and node start order here doesn't guarantee either side of that bridge
    # is actually ready yet. Losing that race throws inside control_node's resource
    # manager and takes its whole controller_manager down - arm included, since they
    # share one process (confirmed on real hardware: every spawner then times out with
    # "Could not contact service .../list_controllers", and the arm doesn't respond to
    # anything either). tcp_controller.launch.py's single-arm+gripper setup hit and fixed
    # this exact race with a 1s head start (see its own delayed_control_node) - but that
    # was tuned for bringing up one robot at a time. Bringing up two at once (leader +
    # follower here) contends for more CPU/network at startup, and 1s wasn't enough:
    # confirmed on real hardware, the gripper driver's own connection attempt was still
    # failing ("Reached maximum retries") a good ~2.5s after control_node started, with
    # tool_communication_node's bridge only having begun setting up ~1.3s prior. 5s gives
    # real margin instead of matching the single-arm case exactly.
    if use_gripper.perform(context) == "true" and use_tool_communication.perform(context) == "true":
        control_node_entry = TimerAction(period=5.0, actions=[control_node])
    else:
        control_node_entry = control_node

    nodes_to_start = [
        control_node_entry,
        dashboard_client_node,
        robot_state_helper_node,
        tool_communication_node,
        controller_stopper_node,
        urscript_interface,
        rsp,
        rviz_node,
    ] + controller_spawners

    # Push everything under namespace (a no-op when namespace is "") so that two
    # instances of this launch file (e.g. leader/follower) can run side by side without
    # node/topic/service name collisions.
    return [GroupAction(actions=[PushRosNamespace(namespace_value), *nodes_to_start])]


def generate_launch_description():
    declared_arguments = []
    # UR specific arguments
    declared_arguments.append(
        DeclareLaunchArgument(
            "ur_type",
            description="Type/series of used UR robot.",
            choices=[
                "ur3",
                "ur5",
                "ur10",
                "ur3e",
                "ur5e",
                "ur7e",
                "ur10e",
                "ur12e",
                "ur16e",
                "ur8long",
                "ur15",
                "ur20",
                "ur30",
            ],
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "robot_ip", description="IP address by which the robot can be reached."
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "namespace",
            default_value="",
            description="ROS namespace to push this robot's nodes under. Required to run "
            "two robots (e.g. leader/follower) at the same time without collisions.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_gripper",
            default_value="false",
            description="Also spawn the Robotiq gripper controllers. Requires a URDF that "
            "exports the Robotiq ros2_control hardware interface (not the case for the "
            "default arm-only description_launchfile/description_file).",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "safety_limits",
            default_value="true",
            description="Enables the safety limits controller if true.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "safety_pos_margin",
            default_value="0.15",
            description="The margin to lower and upper limits in the safety controller.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "safety_k_position",
            default_value="20",
            description="k-position factor in the safety controller.",
        )
    )
    # General arguments
    declared_arguments.append(
        DeclareLaunchArgument(
            "controllers_file",
            default_value=PathJoinSubstitution(
                [FindPackageShare("ur_robot_driver"), "config", "ur_controllers.yaml"]
            ),
            description="YAML file with the controllers configuration.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_launchfile",
            default_value=PathJoinSubstitution(
                [FindPackageShare("ur_robot_driver"), "launch", "ur_rsp.launch.py"]
            ),
            description="Launchfile (absolute path) providing the description. "
            "The launchfile has to start a robot_state_publisher node that "
            "publishes the description topic.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_file",
            default_value=PathJoinSubstitution(
                [FindPackageShare("ur_robot_driver"), "urdf", "ur.urdf.xacro"]
            ),
            description="URDF/XACRO description file (absolute path), forwarded to "
            "description_launchfile as its own 'description_file' argument. Only "
            "meaningful if description_launchfile actually accepts that argument (the "
            "default rsp.launch.py does); pass ur5e_gripper_controlled.urdf.xacro here "
            "together with use_gripper:=true to bring up a Robotiq gripper too.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "com_port",
            default_value="/dev/ttyUSB0",
            description="Serial device a Robotiq gripper is bridged on. Only meaningful "
            "when description_file declares this xacro arg; harmlessly ignored otherwise.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tf_prefix",
            default_value="",
            description="tf_prefix of the joint names, useful for "
            "multi-robot setup. If changed, also joint names in the controllers' configuration "
            "have to be updated.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_mock_hardware",
            default_value="false",
            description="Start robot with mock hardware mirroring command to its states.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "mock_sensor_commands",
            default_value="false",
            description="Enable mock command interfaces for sensors used for simple simulations. "
            "Used only if 'use_mock_hardware' parameter is true.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "headless_mode",
            default_value="false",
            description="Enable headless mode for robot control",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "controller_spawner_timeout",
            default_value="10",
            description="Timeout used when spawning controllers.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "initial_joint_controller",
            default_value="scaled_joint_trajectory_controller",
            choices=[
                "scaled_joint_trajectory_controller",
                "joint_trajectory_controller",
                "forward_velocity_controller",
                "forward_position_controller",
                "freedrive_mode_controller",
                "passthrough_trajectory_controller",
            ],
            description="Initially loaded robot controller.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "activate_joint_controller",
            default_value="true",
            description="Activate loaded joint controller.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument("launch_rviz", default_value="true", description="Launch RViz?")
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "rviz_config_file",
            default_value=PathJoinSubstitution(
                [FindPackageShare("ur_description"), "rviz", "view_robot.rviz"]
            ),
            description="RViz config file (absolute path) to use when launching rviz.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "launch_dashboard_client",
            default_value="true",
            description="Launch Dashboard Client?",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_tool_communication",
            default_value="false",
            description="Only available for e series!",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_parity",
            default_value="0",
            description="Parity configuration for serial communication. Only effective, if "
            "use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_baud_rate",
            default_value="115200",
            description="Baud rate configuration for serial communication. Only effective, if "
            "use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_stop_bits",
            default_value="1",
            description="Stop bits configuration for serial communication. Only effective, if "
            "use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_rx_idle_chars",
            default_value="1.5",
            description="RX idle chars configuration for serial communication. Only effective, "
            "if use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_tx_idle_chars",
            default_value="3.5",
            description="TX idle chars configuration for serial communication. Only effective, "
            "if use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_device_name",
            default_value="/tmp/ttyUR",
            description="File descriptor that will be generated for the tool communication device. "
            "The user has be be allowed to write to this location. "
            "Only effective, if use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_tcp_port",
            default_value="54321",
            description="Remote port that will be used for bridging the tool's serial device. "
            "Only effective, if use_tool_communication is set to True.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "tool_voltage",
            default_value="0",  # 0 being a conservative value that won't destroy anything
            description="Tool voltage that will be setup.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "reverse_ip",
            default_value="0.0.0.0",
            description="IP that will be used for the robot controller to communicate back to the driver.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "script_command_port",
            default_value="50004",
            description="Port that will be opened to forward URScript commands to the robot.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "reverse_port",
            default_value="50001",
            description="Port that will be opened to send cyclic instructions from the driver to the robot controller.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "script_sender_port",
            default_value="50002",
            description="The driver will offer an interface to query the external_control URScript on this port.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "trajectory_port",
            default_value="50003",
            description="Port that will be opened for trajectory control.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            name="update_rate_config_file",
            default_value=[
                PathJoinSubstitution(
                    [
                        FindPackageShare("ur_robot_driver"),
                        "config",
                    ]
                ),
                "/",
                LaunchConfiguration("ur_type"),
                "_update_rate.yaml",
            ],
        )
    )
    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])