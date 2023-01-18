# Settings Guide

## Mouse Settings (mouse_settings.json)

    "idle_thresh"   : Slower than this number means mouse is detecting idle (default 5.0)
    "min_run_cycles": Number of samples to run before starting idle-checking (default 30.0)
    "scale"         : Base number - change this to increase mouse speed by flat multiplier (default 1.0)
    "slow_thresh"   : User speed floor. Above this, mouse accelerates (default 20.0)
    "fast_thresh"   : User speed ceiling. Motion faster than this no longer accelerates. (default 240.0)
    "slow_scale"    : Cursor speed floor. (default 0.2)
    "fast_scale"    : Cursor speed ceiling. (default 3.0)

## State Matrix (st_matrix.json)

    | GESTURE       | IDLE              | MOUSE (Coming soon!)  | KEYBOARD MODE (Coming soon!)  |
    | -----------   | -----------       | -----------           | -----------                   |
    | Up            | Left Click        | -----------           | -----------                   |
    | Down          | Move Mouse        | -----------           | -----------                   |
    | Right         | Scroll            | -----------           | -----------                   |
    | Left          | Wait for Motion   | -----------           | -----------                   |
    | Roll Right    | Scroll Left/Right | -----------           | -----------                   |
    | Roll Left     | Scroll Left/Right | -----------           | -----------                   |
    | Nod Yes       | Double Click      | -----------           | -----------                   |
    | Shake No      | No Operation      | -----------           | -----------                   |

## Operation Mode (operation_mode.json)

Select mode of operation:

Gesture Collection

Standard operation

TV Mode (coming soon)
