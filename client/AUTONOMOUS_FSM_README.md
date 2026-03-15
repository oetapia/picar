# Autonomous Navigation - Hybrid FSM Architecture

## 📋 Overview

This directory contains **two implementations** of autonomous navigation:

1. **`autonomous.py`** - Original implementation (working, tested)
2. **`autonomous_fsm.py`** - New Hybrid FSM implementation (industry-standard architecture)

Both share the same **`autonomous_hooks.py`** - a library of reusable navigation functions.

---

## 🏗️ Architecture

### Hybrid FSM + Decision Tree

```
┌──────────────────────────────────────────────┐
│         AUTONOMOUS NAVIGATION                │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │   PRIORITY 1: EMERGENCY CHECKS     │     │
│  │   - Forward emergency stop         │     │
│  │   - Reverse emergency stop         │     │
│  │   - Predictive braking             │     │
│  └────────────┬───────────────────────┘     │
│               ↓                              │
│  ┌────────────────────────────────────┐     │
│  │   PRIORITY 2: RECOVERY LOGIC       │     │
│  │   - Clear from emergency zones     │     │
│  │   - Choose safest direction        │     │
│  └────────────┬───────────────────────┘     │
│               ↓                              │
│  ┌────────────────────────────────────┐     │
│  │   PRIORITY 3: TRAPPED CHECK        │     │
│  │   - No safe path available         │     │
│  └────────────┬───────────────────────┘     │
│               ↓                              │
│  ┌────────────────────────────────────┐     │
│  │   PRIORITY 4: NAVIGATION TREE      │     │
│  │   - CRUISE (>90cm)                 │     │
│  │   - MEDIUM (60-90cm)               │     │
│  │   - SLOW (45-60cm)                 │     │
│  │   - CRAWL (35-45cm)                │     │
│  │   - TACTICAL_REVERSE (<35cm)       │     │
│  └────────────────────────────────────┘     │
└──────────────────────────────────────────────┘
```

---

## 📁 File Structure

```
client/
├── autonomous.py           # Original implementation (still works!)
├── autonomous_fsm.py       # NEW: Hybrid FSM implementation
├── autonomous_hooks.py     # NEW: Shared reusable functions
├── picar_client.py         # Existing API client
└── AUTONOMOUS_FSM_README.md  # This file
```

---

## 🎯 Finite State Machine States

### State Diagram

```
    START
      ↓
   STOPPED
      ↓
   ┌──────────────┐
   │   CRUISE     │ ←─────────────┐
   │   MEDIUM     │                │
   │   SLOW       │                │
   │   CRAWL      │                │
   │ TACTICAL_REV │                │
   └──────┬───────┘                │
          ↓                        │
    EMERGENCY_STOP                 │
          ↓                        │
      RECOVERY ─────────────────────┘
          ↓
      TRAPPED
```

### State Definitions

| State | Description | Speed | Conditions |
|-------|-------------|-------|------------|
| **STOPPED** | Idle, no movement | 0% | Initial state |
| **CRUISE** | Full speed forward | 35% | Front > 90cm |
| **MEDIUM** | Medium speed | 25% | Front 60-90cm |
| **SLOW** | Slow speed | 18% | Front 45-60cm |
| **CRAWL** | Very slow | 12% | Front 35-45cm |
| **TACTICAL_REVERSE** | Strategic reverse | -22% | Front < 35cm, rear clear |
| **EMERGENCY_STOP** | Immediate stop | 0% | Front/Rear < 50cm |
| **RECOVERY** | Clearing emergency | Varies | After emergency stop |
| **TRAPPED** | No safe path | 0% | Front < 25cm, rear < 35cm |

---

## 🔧 Key Features

### 1. **Clean Separation of Concerns**
```python
# Hooks handle low-level operations
hooks.execute_forward(client, speed, left, right)

# FSM handles high-level decisions
state = self._decide_navigation_state(sensor_data)
```

### 2. **Priority-Based Decision Making**
```
Priority 1: Emergency (immediate safety)
Priority 2: Recovery (clear from danger)
Priority 3: Trapped (no escape)
Priority 4: Navigation (normal operation)
```

### 3. **Reusable Components**
All navigation logic extracted into testable hooks:
- Sensor reading
- Safety checks
- Steering calculation
- Action execution
- Display formatting

### 4. **State History & Debugging**
```python
# Uncomment in _transition_to() for debugging:
print(f"\r[FSM] {old_state.name} → {new_state.name}")
```

---

## 🚀 Usage

### Running FSM Version

```bash
# From client directory
python3 autonomous_fsm.py

# Or import in your code
from autonomous_fsm import AutonomousFSM
driver = AutonomousFSM(client)
driver.start()
```

### Running Original Version

```bash
# Still works exactly as before
python3 autonomous.py
```

### Controls

Both implementations support the same controls:

- **G** - Start autonomous mode
- **SPACE** - Stop autonomous mode
- **Q** - Quit program

---

## 📊 Comparison: Original vs FSM

| Aspect | Original (`autonomous.py`) | FSM (`autonomous_fsm.py`) |
|--------|---------------------------|---------------------------|
| **Architecture** | Monolithic if-elif chain | Hybrid FSM + Decision Tree |
| **Maintainability** | ⚠️ Moderate | ✅ High |
| **Debuggability** | ⚠️ Print statements | ✅ State transitions + hooks |
| **Testability** | ⚠️ Hard to unit test | ✅ Easy (hooks are testable) |
| **Code Organization** | ⚠️ Embedded logic | ✅ Separated concerns |
| **State Visibility** | ⚠️ Implicit | ✅ Explicit enum states |
| **Performance** | ✅ Same | ✅ Same |
| **Safety** | ✅ Same logic | ✅ Same logic |
| **Extensibility** | ⚠️ Moderate | ✅ Easy (add states) |

---

## 🧪 Testing Recommendations

### 1. **Test in Safe Environment**
```bash
# Start in open area
python3 autonomous_fsm.py
# Press 'g' to start
```

### 2. **Verify State Transitions**
Watch console output for state information:
- `🟢 CRUISE` - Cruising at full speed
- `🟢 MEDIUM` - Medium speed
- `🟢 SLOW` - Slowing down
- `🟢 CRAWL` - Very slow
- `🔵 REVERSE` - Backing up
- `🚨 EMERGENCY STOP!` - Emergency stop triggered
- `🔄 RECOVERY` - Recovering from emergency

### 3. **Test Emergency Scenarios**
- **Front obstacle**: Approach wall - should stop at 50cm
- **Rear obstacle**: Reverse toward wall - should stop at 50cm
- **Trapped**: Block both front and rear

### 4. **Compare Implementations**
```bash
# Test original
python3 autonomous.py  # Press 'g'

# Test FSM
python3 autonomous_fsm.py  # Press 'g'

# Compare behavior
```

---

## 🎨 Customization

### Adjusting Parameters

All parameters are in `autonomous_hooks.py`:

```python
# Speed settings
CRUISE_SPEED = 35  # Increase for faster cruise
MEDIUM_SPEED = 25
SLOW_SPEED = 18

# Distance thresholds
EMERGENCY_STOP_DIST = 50  # Increase for earlier stopping
VERY_SAFE_DIST = 90       # Increase for more conservative
```

### Adding New States

1. Add to `NavigationState` enum:
```python
class NavigationState(Enum):
    # ... existing states ...
    YOUR_NEW_STATE = auto()
```

2. Add handler:
```python
def _handle_your_new_state(self, sensor_data):
    # Your custom logic
    pass
```

3. Update state handlers dict:
```python
state_handlers = {
    # ... existing handlers ...
    NavigationState.YOUR_NEW_STATE: self._handle_your_new_state,
}
```

4. Add to decision tree:
```python
def _decide_navigation_state(self, sensor_data):
    # Add your condition
    if your_condition(sensor_data):
        return NavigationState.YOUR_NEW_STATE
```

---

## 🐛 Debugging

### Enable State Transition Logging

In `autonomous_fsm.py`, uncomment line in `_transition_to()`:

```python
def _transition_to(self, new_state: NavigationState):
    if new_state != self.state:
        old_state = self.state
        self.state = new_state
        print(f"\r[FSM] {old_state.name} → {new_state.name}")  # Uncomment this
```

Output:
```
[FSM] STOPPED → CRUISE
[FSM] CRUISE → MEDIUM
[FSM] MEDIUM → SLOW
[FSM] SLOW → EMERGENCY_STOP
```

### Testing Individual Hooks

```python
# Test hooks independently
from autonomous_hooks import *

# Test steering calculation
servo, label = calculate_steering(left_dist=30, right_dist=80)
print(f"Servo: {servo}°, Label: {label}")

# Test emergency check
is_emergency = check_emergency_forward("forward", 45)
print(f"Emergency: {is_emergency}")
```

---

## 📈 Performance Metrics

### Timing
- **Poll interval**: 0.05s (20Hz sensor reading)
- **Display update**: 0.2s (5Hz OLED refresh)
- **Emergency response**: <0.1s (immediate)

### Safety Margins
- **Emergency threshold**: 50cm (accounts for 250-400ms lag)
- **Final stop distance**: ~25-35cm (with reaction delay)
- **Safe cruise distance**: >90cm

---

## 🎓 Industry Standards Reference

This implementation follows best practices from:

### Automotive Systems
- **ISO 26262** - Functional safety (hierarchical decision making)
- **AUTOSAR** - Automotive software architecture (state machines)

### Robotics
- **ROS Navigation Stack** - Layered navigation architecture
- **Behavior Trees** - Hierarchical behavior composition

### Aerospace
- **DO-178C** - Software safety (clear state transitions)
- **ARINC 653** - Partitioning (separated concerns)

---

## 🔮 Future Enhancements

### Easy to Add
- [ ] **Path planning** - Add PLANNING state
- [ ] **Learning mode** - Log state transitions for analysis
- [ ] **Obstacle avoidance** - Enhanced steering algorithms
- [ ] **Speed profiles** - Dynamic speed based on environment

### Moderate Complexity
- [ ] **Behavior Trees** - Replace decision tree with BT
- [ ] **SLAM integration** - Add mapping capability
- [ ] **Multi-sensor fusion** - Kalman filtering

### Advanced
- [ ] **Model Predictive Control** - Optimize trajectories
- [ ] **Machine Learning** - Learn optimal navigation
- [ ] **Swarm coordination** - Multiple cars

---

## 🏆 Benefits of FSM Approach

### For Development
- ✅ **Easy to understand** - Clear state names
- ✅ **Easy to test** - Each state testable independently
- ✅ **Easy to extend** - Add states without breaking existing code
- ✅ **Easy to debug** - State history shows execution flow

### For Maintenance
- ✅ **Modular** - Change one state without affecting others
- ✅ **Documented** - States are self-documenting
- ✅ **Predictable** - Explicit state transitions
- ✅ **Scalable** - Grows cleanly with new features

### For Safety
- ✅ **Priority-based** - Critical checks always run first
- ✅ **Explicit states** - No hidden/implicit states
- ✅ **Testable safety** - Each safety check is a function
- ✅ **Auditable** - State transitions can be logged/reviewed

---

## 📚 Further Reading

- [Finite State Machines in Games](https://gameprogrammingpatterns.com/state.html)
- [ROS Navigation Stack Architecture](http://wiki.ros.org/navigation)
- [Autonomous Vehicle Safety](https://www.iso.org/standard/68383.html)

---

## 🤝 Contributing

When modifying navigation logic:

1. **Add hooks first** - Put reusable logic in `autonomous_hooks.py`
2. **Use hooks in FSM** - Keep FSM focused on decisions
3. **Test hooks** - Write unit tests for new hooks
4. **Document states** - Update this README with new states

---

## 📝 License

Same as parent project.

---

## ✨ Credits

**Architecture**: Industry-standard Hybrid FSM + Decision Tree
**Pattern**: Automotive/Robotics best practices
**Implementation**: Modular, testable, maintainable

---

**Happy autonomous navigation! 🚗**
