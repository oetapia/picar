# Autonomous Driving Improvement Roadmap

**Last Updated:** March 16, 2026  
**Status:** Planning Phase  
**Current System:** Hybrid FSM with Basic Navigation

---

## 📊 Current System Assessment

### ✅ Strengths (Industry-Aligned)
- ✓ Hybrid Finite State Machine architecture
- ✓ Priority-based safety system (Emergency → Recovery → Navigation)
- ✓ Predictive braking with approach rate calculation
- ✓ Modular design with reusable hooks
- ✓ Emergency stop and recovery mechanisms

### ⚠️ Gaps vs. Industry Standards
- ❌ No sensor fusion
- ❌ No localization/odometry
- ❌ No path planning
- ❌ No object tracking
- ❌ Open-loop control (no feedback)
- ❌ Reactive only (no goal-oriented behavior)

---

## 🎯 Implementation Phases

### **PHASE 1: Sensor Fusion & Perception** 🔴 Priority: HIGH
**Goal:** Create unified perception layer with IMU integration  
**Estimated Effort:** 2-3 sessions  
**Dependencies:** MPU6050 sensor already available

#### Tasks:
- [ ] 1.1 Create `PerceptionSystem` class
  - [ ] Design sensor fusion architecture
  - [ ] Implement confidence-weighted sensor fusion
  - [ ] Add obstacle tracking data structure
  
- [ ] 1.2 Integrate IMU (MPU6050) into autonomous loop
  - [ ] Add IMU reading to sensor poll cycle
  - [ ] Validate IMU data quality
  - [ ] Create IMU data structure
  
- [ ] 1.3 Implement basic sensor fusion
  - [ ] Fuse ToF + Ultrasonic with confidence weights
  - [ ] Use IMU to validate motion state
  - [ ] Add sensor health monitoring
  
- [ ] 1.4 Add obstacle persistence tracking
  - [ ] Track obstacles over time
  - [ ] Calculate obstacle velocity
  - [ ] Decay old obstacle data

**Success Criteria:**
- ✓ Unified obstacle list from multiple sensors
- ✓ Confidence scores for each detection
- ✓ IMU data integrated into decision making
- ✓ Reduced false positives from sensor noise

**Files to Create/Modify:**
- `client/perception.py` (NEW)
- `client/autonomous_hooks.py` (MODIFY - add IMU support)
- `client/autonomous.py` (MODIFY - integrate perception)
- `client/autonomous_fsm.py` (MODIFY - integrate perception)

---

### **PHASE 2: Odometry & State Estimation** 🟡 Priority: MEDIUM
**Goal:** Track position and velocity for dead reckoning  
**Estimated Effort:** 2-3 sessions  
**Dependencies:** Phase 1 complete (IMU integration)

#### Tasks:
- [ ] 2.1 Create `OdometrySystem` class
  - [ ] Design state estimation architecture
  - [ ] Implement position tracking (x, y, theta)
  - [ ] Implement velocity estimation
  
- [ ] 2.2 Implement dead reckoning
  - [ ] Use motor speed for velocity estimation
  - [ ] Use gyro for heading changes
  - [ ] Use accelerometer for velocity validation
  
- [ ] 2.3 Calibrate motion model
  - [ ] Measure actual speed vs motor command
  - [ ] Measure turning radius vs servo angle
  - [ ] Create lookup tables for accuracy
  
- [ ] 2.4 Add motion validation
  - [ ] Compare IMU motion with expected motion
  - [ ] Detect wheel slip
  - [ ] Detect collisions (sudden deceleration)

**Success Criteria:**
- ✓ Position tracking with < 20% drift over 10 meters
- ✓ Velocity estimation within 10% of actual
- ✓ Heading estimation within 5 degrees
- ✓ Collision detection working

**Files to Create/Modify:**
- `client/odometry.py` (NEW)
- `client/autonomous_hooks.py` (MODIFY - add odometry data)
- `sensors/accelerometer.py` (MODIFY - enhance for odometry)

---

### **PHASE 3: Behavior Planning & Maneuvers** 🔴 Priority: HIGH
**Goal:** Add intelligent maneuver selection beyond basic navigation  
**Estimated Effort:** 3-4 sessions  
**Dependencies:** Phase 1 complete

#### Tasks:
- [ ] 3.1 Create `BehaviorPlanner` class
  - [ ] Design maneuver primitive structure
  - [ ] Implement cost-based maneuver selection
  - [ ] Add context awareness
  
- [ ] 3.2 Implement maneuver primitives
  - [ ] Wall following mode
  - [ ] Corridor centering mode
  - [ ] Obstacle avoidance strategies
  - [ ] Three-point turn
  - [ ] Parallel parking (bonus)
  
- [ ] 3.3 Add maneuver feasibility checking
  - [ ] Check sensor requirements
  - [ ] Check space requirements
  - [ ] Check safety constraints
  
- [ ] 3.4 Integrate with FSM
  - [ ] Add MANEUVER states to FSM
  - [ ] Add maneuver execution logic
  - [ ] Add maneuver completion detection

**Success Criteria:**
- ✓ Can follow walls at consistent distance
- ✓ Can center in corridors
- ✓ Can execute three-point turn when stuck
- ✓ Smooth transitions between maneuvers

**Files to Create/Modify:**
- `client/behavior_planner.py` (NEW)
- `client/maneuvers.py` (NEW)
- `client/autonomous_fsm.py` (MODIFY - add maneuver states)
- `client/autonomous_hooks.py` (MODIFY - add maneuver execution)

---

### **PHASE 4: Path Planning** 🟡 Priority: MEDIUM
**Goal:** Enable goal-oriented navigation with obstacle mapping  
**Estimated Effort:** 3-4 sessions  
**Dependencies:** Phase 1, 2 complete

#### Tasks:
- [ ] 4.1 Create `PathPlanner` class
  - [ ] Design occupancy grid structure
  - [ ] Implement grid update logic
  - [ ] Add goal setting mechanism
  
- [ ] 4.2 Implement occupancy grid mapping
  - [ ] Convert sensor data to grid cells
  - [ ] Mark occupied/free cells
  - [ ] Decay old obstacle data
  
- [ ] 4.3 Implement A* path planning
  - [ ] Create A* search algorithm
  - [ ] Add heuristic function
  - [ ] Generate waypoint list
  
- [ ] 4.4 Implement path following
  - [ ] Create path follower controller
  - [ ] Add waypoint tracking
  - [ ] Add re-planning on obstacle detection

**Success Criteria:**
- ✓ Can navigate to specified (x, y) goal
- ✓ Avoids known obstacles
- ✓ Re-plans when path blocked
- ✓ Updates map as it explores

**Files to Create/Modify:**
- `client/path_planner.py` (NEW)
- `client/occupancy_grid.py` (NEW)
- `client/autonomous_fsm.py` (MODIFY - add path following states)

---

### **PHASE 5: Control Optimization** 🟢 Priority: LOW
**Goal:** Smooth motion with closed-loop control  
**Estimated Effort:** 2 sessions  
**Dependencies:** Phase 2 complete

#### Tasks:
- [ ] 5.1 Create `PIDController` class
  - [ ] Implement PID algorithm
  - [ ] Add anti-windup
  - [ ] Add output clamping
  
- [ ] 5.2 Implement speed PID controller
  - [ ] Measure actual speed
  - [ ] Tune PID parameters
  - [ ] Smooth acceleration/deceleration
  
- [ ] 5.3 Implement steering PID controller
  - [ ] Measure actual heading
  - [ ] Tune PID parameters
  - [ ] Smooth turning
  
- [ ] 5.4 Add jerk minimization
  - [ ] Limit acceleration changes
  - [ ] Limit steering rate changes
  - [ ] Create motion profile generator

**Success Criteria:**
- ✓ Smooth speed transitions (no jerky motion)
- ✓ Accurate speed tracking within 5%
- ✓ Smooth steering (no oscillation)
- ✓ Comfortable motion for passengers/payload

**Files to Create/Modify:**
- `client/pid_controller.py` (NEW)
- `client/motion_controller.py` (NEW)
- `client/autonomous_hooks.py` (MODIFY - use PID control)

---

## 📐 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               PERCEPTION LAYER (Phase 1)               │ │
│  │  • Sensor Fusion (ToF + Ultrasonic + IMU)             │ │
│  │  • Obstacle Tracking                                   │ │
│  │  • Confidence Scoring                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            LOCALIZATION LAYER (Phase 2)                │ │
│  │  • Odometry / Dead Reckoning                          │ │
│  │  • Position Estimation (x, y, θ)                      │ │
│  │  • Velocity Estimation                                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              PLANNING LAYER (Phase 3, 4)               │ │
│  │  • Behavior Planning (Maneuver Selection)             │ │
│  │  • Path Planning (A* / Occupancy Grid)                │ │
│  │  • Collision Avoidance                                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               CONTROL LAYER (Phase 5)                  │ │
│  │  • PID Speed Controller                                │ │
│  │  • PID Steering Controller                             │ │
│  │  • Motion Profile Generation                           │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               EXECUTION LAYER (Existing)               │ │
│  │  • Hybrid FSM                                          │ │
│  │  • Emergency Systems                                   │ │
│  │  • Motor & Servo Commands                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📚 Industry Standards Reference

### SAE Autonomy Levels (Adapted for Toy Car)

| Level | Description | Current Status | Target |
|-------|-------------|----------------|--------|
| **Level 0** | No automation | ❌ | - |
| **Level 1** | Driver assistance (cruise control) | ❌ | - |
| **Level 2** | Partial automation (steering + speed) | ✅ **CURRENT** | - |
| **Level 3** | Conditional automation (monitors environment) | 🟡 After Phase 1 | ✅ **TARGET** |
| **Level 4** | High automation (handles all driving in area) | 🟡 After Phase 4 | 🎯 **STRETCH** |
| **Level 5** | Full automation (everywhere) | ❌ | - |

### ISO 26262 Compliance (Functional Safety)
- ✅ Emergency stop system (ASIL-D equivalent)
- ✅ Fail-safe default behaviors
- ✅ Redundant safety checks
- 🟡 Sensor validation needed (Phase 1)
- 🟡 Plausibility checks needed (Phase 2)

---

## 🔧 Technical Specifications

### Sensor Suite
| Sensor | Use Case | Update Rate | Range |
|--------|----------|-------------|-------|
| **VL53L0X ToF (2x)** | Front obstacle detection | 20 Hz | 0-200 cm |
| **HC-SR04 Ultrasonic** | Rear obstacle detection | 10 Hz | 2-400 cm |
| **MPU6050 IMU** | Motion sensing, stability | 100 Hz | 3-axis accel + gyro |

### Performance Targets
| Metric | Current | Phase 1 | Phase 4 | Phase 5 |
|--------|---------|---------|---------|---------|
| **Obstacle Detection Rate** | 90% | 95% | 98% | 98% |
| **False Positive Rate** | 15% | 8% | 5% | 5% |
| **Position Accuracy** | N/A | ±50cm | ±20cm | ±10cm |
| **Speed Control Error** | ±30% | ±30% | ±20% | ±5% |
| **Collision Avoidance** | 85% | 90% | 95% | 98% |

---

## 📋 Quick Start Guide

### Working on Phase 1 (Sensor Fusion)
1. Read this document thoroughly
2. Review existing sensor code: `sensors/dual_tof.py`, `sensors/hcsr04.py`, `sensors/accelerometer.py`
3. Create `client/perception.py` starting with basic structure
4. Test sensor fusion with real hardware
5. Integrate into `autonomous.py` and `autonomous_fsm.py`
6. Mark tasks as complete in this document

### Testing Each Phase
- **Phase 1:** Test with stationary obstacles, moving obstacles
- **Phase 2:** Drive in squares, measure drift
- **Phase 3:** Test each maneuver in isolation
- **Phase 4:** Set goals, observe path following
- **Phase 5:** Measure speed accuracy, smoothness

---

## 🎯 Success Metrics (Overall)

**After All Phases Complete:**
- ✓ Navigate from Point A to Point B autonomously
- ✓ Avoid dynamic obstacles
- ✓ Recover from getting stuck (three-point turn)
- ✓ Follow walls smoothly
- ✓ Center in corridors
- ✓ Smooth, comfortable motion
- ✓ < 5% collision rate in testing
- ✓ Position error < 10cm over 10m

---

## 🔄 Iteration Strategy

Each phase should follow this workflow:
1. **Design** - Plan the architecture
2. **Implement** - Write the code
3. **Unit Test** - Test components in isolation
4. **Integration Test** - Test with full system
5. **Validation** - Test with real hardware
6. **Document** - Update this roadmap
7. **Refine** - Iterate based on results

---

## 📝 Notes & Considerations

### Hardware Limitations
- **Compute:** Limited CPU on Pico (prioritize efficient algorithms)
- **Memory:** Limited RAM (use efficient data structures)
- **Sensors:** Noisy data (use filtering and fusion)
- **Actuators:** Open-loop motor control (use odometry feedback)

### Development Tips
- Start simple, add complexity gradually
- Test each component independently
- Use simulation when possible (before hardware testing)
- Keep safety as top priority
- Document assumptions and calibration values

### Future Enhancements (Post-Roadmap)
- 🎯 Visual odometry (camera-based)
- 🎯 Machine learning for obstacle classification
- 🎯 Multi-robot coordination
- 🎯 SLAM (Simultaneous Localization and Mapping)
- 🎯 Semantic mapping (room recognition)

---

## 📞 Getting Help

- Review existing code comments
- Check sensor README files in `sensors/` directory
- Test incrementally (don't implement everything at once)
- Use OLED display for debugging status
- Log sensor data for post-analysis

---

**Ready to start? Begin with Phase 1, Task 1.1!** 🚀

_Last Updated: March 16, 2026_
