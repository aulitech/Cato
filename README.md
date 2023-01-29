# Cato docs

Hello and welcome to CATO, an aulitech alternative communication device for everyone

This device can be used as
    A bluetooth mouse
    A television remote

## Programming the device

coming soon

# Using the device

Cato connects to devices via bluetooth under the name "Cato"

It must be mounted narrow-end first, on the left side of a pair of glasses (to be opened to other orientations soon)

When booted or restarted, the device runs a calibration check, in which it must be held still

## Once connected

The board alternates between two modes:

Mode 1: Detecting Gestures

Mode 2: Moving the mouse

## Mode 1: Detecting Gestures

Cato detects nods in each of 4 directions (up, down, right, left) 

It detects rolling (left ear -> left shoulder; right ear -> right shoulder)

It detects "Yes" and "No"

## Mode 2: Mouse Movement

    Cato moves the cursor on screen until the user idles the cursor for a moment

    It then gently jiggles the cursor to indicate completion of mouse movement

    It then re-enters gesture detection mode

# Settings Guide

## Mouse Settings

    "idle_thresh"   : Slower than this number means mouse is detecting idle (default 5.0)
    "min_run_cycles": Number of samples to run before starting idle-checking (default 30.0)
    "scale"         : Base number - change this to increase mouse speed by flat multiplier (default 1.0)
    "slow_thresh"   : User speed floor. Above this, mouse accelerates (default 20.0)
    "fast_thresh"   : User speed ceiling. Motion faster than this no longer accelerates. (default 240.0)
    "slow_scale"    : Cursor speed floor. (default 0.2)
    "fast_scale"    : Cursor speed ceiling. (default 3.0)

## State Matrix

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

## Operation Mode

    Select mode of operation:

    Gesture Collection

    Standard operation

    TV Mode (coming soon)
