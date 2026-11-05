#pragma once

#include <cstdint>
#include <cmath>

typedef int8_t   s8;
typedef uint8_t  u8;
typedef int16_t  s16;
typedef uint16_t u16;
typedef int32_t  s32;
typedef uint32_t u32;
typedef int64_t  s64;
typedef uint64_t u64;
typedef float    f32;
typedef double   f64;

typedef f32 Vec3f[3];
typedef s16 Vec3s[3];

// Action Groups
#define ACT_GROUP_MASK       0x000001C0
#define ACT_GROUP_STATIONARY 0x00000000
#define ACT_GROUP_MOVING     0x00000040
#define ACT_GROUP_AIRBORNE   0x00000080
#define ACT_GROUP_SUBMERGED  0x000000C0
#define ACT_GROUP_CUTSCENE   0x00000100
#define ACT_GROUP_AUTOMATIC  0x00000140
#define ACT_GROUP_OBJECT     0x00000180

// Action Flags
#define ACT_FLAG_STATIONARY                  (1 << 9)
#define ACT_FLAG_MOVING                      (1 << 10)
#define ACT_FLAG_AIR                         (1 << 11)
#define ACT_FLAG_INTANGIBLE                  (1 << 12)
#define ACT_FLAG_SWIMMING                    (1 << 13)
#define ACT_FLAG_METAL_WATER                 (1 << 14)
#define ACT_FLAG_SHORT_HITBOX                (1 << 15)
#define ACT_FLAG_RIDING_SHELL                (1 << 16)
#define ACT_FLAG_INVULNERABLE                (1 << 17)
#define ACT_FLAG_BUTT_OR_STOMACH_SLIDE       (1 << 18)
#define ACT_FLAG_DIVING                      (1 << 19)
#define ACT_FLAG_ON_POLE                     (1 << 20)
#define ACT_FLAG_HANGING                     (1 << 21)
#define ACT_FLAG_IDLE                        (1 << 22)
#define ACT_FLAG_ATTACKING                   (1 << 23)
#define ACT_FLAG_ALLOW_VERTICAL_WIND_ACTION  (1 << 24)
#define ACT_FLAG_CONTROL_JUMP_HEIGHT         (1 << 25)
#define ACT_FLAG_WATER_OR_TEXT               (1 << 26)

// Specific Actions
#define ACT_IDLE                     0x0C400201
#define ACT_WALKING                  0x04000440
#define ACT_DECELERATING             0x0400044A
#define ACT_BRAKING                  0x04000445 // Skid 180
#define ACT_CROUCHING                0x0C008220
#define ACT_START_CROUCHING          0x0C008221
#define ACT_STOP_CROUCHING           0x0C008222
#define ACT_JUMP                     0x03000880
#define ACT_DOUBLE_JUMP              0x03000881
#define ACT_TRIPLE_JUMP              0x01000882
#define ACT_BACKFLIP                 0x01000883
#define ACT_LONG_JUMP                0x03000888
#define ACT_DIVE                     0x0188088A
#define ACT_DIVE_SLIDE               0x00880456
#define ACT_GROUND_POUND             0x008008A9
#define ACT_GROUND_POUND_LAND        0x00800236
#define ACT_SLIDE_KICK               0x01800458
#define ACT_SLIDE_KICK_SLIDE         0x00800459
#define ACT_WALL_KICK_AIR            0x03000886
#define ACT_PUNCHING                 0x00800380
#define ACT_HOLDING_BOWSER           0x000008FF // Margit Tail Spin

// Controller Buttons
#define INPUT_A_PRESSED              0x0001
#define INPUT_A_DOWN                 0x0002
#define INPUT_B_PRESSED              0x0004
#define INPUT_B_DOWN                 0x0008
#define INPUT_Z_PRESSED              0x0010
#define INPUT_Z_DOWN                 0x0020
#define INPUT_NONZERO_ANALOG         0x0040

struct MarioState {
    u32 action;
    u32 prevAction;
    u16 actionTimer;
    u32 flags;

    // Movement
    f32 forwardVel;
    Vec3f vel;
    Vec3f pos;
    Vec3s faceAngle;
    Vec3s angleVel;

    // Floor & Wall state
    f32 floorHeight;
    bool isGrounded;
    bool isAgainstWall;
    Vec3f wallNormal;

    // Boss Interaction (Margit Tail)
    bool isHoldingBoss;
    uintptr_t bossEntityPtr;
    f32 bossSpinSpeed;
    f32 bossAngle;

    // Controller Inputs (Normalized)
    f32 intendedMag;
    s16 intendedYaw;
    u16 input;
};
