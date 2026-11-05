#include "sm64_physics.h"
#include <cmath>
#include <algorithm>

namespace SM64 {

static constexpr f32 MAX_WALK_SPEED = 34.0f;
static constexpr f32 WALK_ACCEL = 2.2f;
static constexpr f32 GROUND_FRICTION = 0.88f;
static constexpr f32 GRAVITY = 2.4f;
static constexpr f32 TERMINAL_VEL = -52.0f;

static int s_landTimer = 100;
static u32 s_lastJumpType = ACT_IDLE;

void InitMario(MarioState* m) {
    m->action = ACT_IDLE;
    m->prevAction = ACT_IDLE;
    m->actionTimer = 0;
    m->flags = ACT_FLAG_STATIONARY;
    m->forwardVel = 0.0f;
    m->vel[0] = 0.0f;
    m->vel[1] = 0.0f;
    m->vel[2] = 0.0f;
    m->faceAngle[0] = 0;
    m->faceAngle[1] = 0;
    m->faceAngle[2] = 0;
    m->angleVel[0] = 0;
    m->angleVel[1] = 0;
    m->angleVel[2] = 0;
    m->floorHeight = 0.0f;
    m->isGrounded = true;
    m->isAgainstWall = false;
    m->isHoldingBoss = false;
    m->bossEntityPtr = 0;
    m->bossSpinSpeed = 0.0f;
    m->bossAngle = 0.0f;
    m->intendedMag = 0.0f;
    m->intendedYaw = 0;
    m->input = 0;
}

void SetAction(MarioState* m, u32 newAction) {
    m->prevAction = m->action;
    m->action = newAction;
    m->actionTimer = 0;
}

void ProcessInputs(
    MarioState* m,
    bool keyW, bool keyA, bool keyS, bool keyD,
    bool spacePressed, bool spaceDown,
    bool rmbDown,
    bool lmbPressed,
    bool keyEPressed,
    float mouseDeltaX,
    float cameraYaw
) {
    m->input = 0;
    if (spacePressed) m->input |= INPUT_A_PRESSED;
    if (spaceDown)    m->input |= INPUT_A_DOWN;
    if (lmbPressed)   m->input |= INPUT_B_PRESSED;
    if (rmbDown)      m->input |= INPUT_Z_DOWN;

    float inputX = 0.0f;
    float inputZ = 0.0f;
    if (keyD) inputX += 1.0f;
    if (keyA) inputX -= 1.0f;
    if (keyW) inputZ += 1.0f;
    if (keyS) inputZ -= 1.0f;

    float mag = std::sqrt(inputX * inputX + inputZ * inputZ);
    if (mag > 0.05f) {
        m->intendedMag = MAX_WALK_SPEED;
        m->input |= INPUT_NONZERO_ANALOG;
        m->intendedYaw = RadToS16(cameraYaw);
        m->faceAngle[1] = m->intendedYaw;
    } else {
        m->intendedMag = 0.0f;
    }

    if (m->isHoldingBoss) {
        float spinInput = std::abs(mouseDeltaX) > 0.5f ? mouseDeltaX * 0.008f : 0.06f;
        m->bossSpinSpeed = std::clamp(m->bossSpinSpeed + spinInput, -0.35f, 0.35f);
        if (std::abs(mouseDeltaX) <= 0.5f) {
            m->bossSpinSpeed *= 0.99f;
        }
        m->bossAngle += m->bossSpinSpeed;
    }
}

static void TriggerGroundJump(MarioState* m) {
    m->isGrounded = false;
    if (m->input & INPUT_Z_DOWN) {
        if (m->input & INPUT_NONZERO_ANALOG) {
            // LONG JUMP ("Yahoo!")
            SetAction(m, ACT_LONG_JUMP);
            m->vel[1] = 26.0f;
            m->forwardVel = 50.0f;
            s_lastJumpType = ACT_IDLE;
        } else {
            // BACKFLIP (Salto mortal)
            SetAction(m, ACT_BACKFLIP);
            m->vel[1] = 48.0f;
            m->forwardVel = -18.0f;
            s_lastJumpType = ACT_IDLE;
        }
        return;
    }

    // Combo clássico: Single Jump -> Double Jump -> Triple Jump
    if (s_landTimer < 25 && s_lastJumpType == ACT_JUMP) {
        SetAction(m, ACT_DOUBLE_JUMP);
        m->vel[1] = 44.0f;
        s_lastJumpType = ACT_DOUBLE_JUMP;
    } else if (s_landTimer < 25 && s_lastJumpType == ACT_DOUBLE_JUMP && (m->input & INPUT_NONZERO_ANALOG)) {
        SetAction(m, ACT_TRIPLE_JUMP);
        m->vel[1] = 54.0f;
        m->forwardVel = std::max(m->forwardVel, 36.0f);
        s_lastJumpType = ACT_IDLE;
    } else {
        SetAction(m, ACT_JUMP);
        m->vel[1] = 34.0f;
        s_lastJumpType = ACT_JUMP;
    }
}

void Step(MarioState* m, float dt) {
    m->actionTimer++;
    if (m->isGrounded) {
        s_landTimer++;
    }

    if (m->isGrounded) {
        if (m->input & INPUT_A_PRESSED) {
            TriggerGroundJump(m);
        } else if ((m->input & INPUT_Z_DOWN) && (m->input & INPUT_B_PRESSED)) {
            SetAction(m, ACT_SLIDE_KICK);
            m->isGrounded = false;
            m->vel[1] = 16.0f;
            m->forwardVel = 42.0f;
        } else if (m->input & INPUT_B_PRESSED) {
            SetAction(m, ACT_PUNCHING);
            m->forwardVel = 22.0f;
        } else if (m->input & INPUT_NONZERO_ANALOG) {
            SetAction(m, ACT_WALKING);
            m->forwardVel = std::min(m->forwardVel + WALK_ACCEL, MAX_WALK_SPEED);
        } else {
            m->forwardVel *= GROUND_FRICTION;
            if (std::abs(m->forwardVel) < 0.5f) {
                m->forwardVel = 0.0f;
                SetAction(m, ACT_IDLE);
            } else {
                SetAction(m, ACT_DECELERATING);
            }
        }
    } else {
        if (m->action == ACT_GROUND_POUND) {
            if (m->actionTimer < 7) {
                m->vel[1] = 0.0f;
                m->forwardVel = 0.0f;
            } else {
                m->vel[1] = -48.0f;
            }
        } else {
            m->vel[1] -= GRAVITY;
            if (m->vel[1] < TERMINAL_VEL) m->vel[1] = TERMINAL_VEL;

            if ((m->input & INPUT_Z_DOWN) && m->action != ACT_LONG_JUMP && m->actionTimer > 3) {
                SetAction(m, ACT_GROUND_POUND);
                m->vel[1] = 0.0f;
                m->forwardVel = 0.0f;
            } else if ((m->input & INPUT_B_PRESSED) && m->action != ACT_DIVE && m->action != ACT_SLIDE_KICK) {
                SetAction(m, ACT_DIVE);
                m->vel[1] = 14.0f;
                m->forwardVel = 44.0f;
            } else if (m->isAgainstWall && (m->input & INPUT_A_PRESSED) && m->actionTimer > 3) {
                SetAction(m, ACT_WALL_KICK_AIR);
                m->faceAngle[1] += 0x8000;
                m->vel[1] = 46.0f;
                m->forwardVel = 28.0f;
            } else if (m->input & INPUT_NONZERO_ANALOG) {
                if (m->forwardVel < 24.0f && m->action != ACT_BACKFLIP) {
                    m->forwardVel += 1.0f;
                }
            }
        }
    }

    float rad = S16ToRad(m->faceAngle[1]);
    m->vel[0] = std::sin(rad) * m->forwardVel;
    m->vel[2] = std::cos(rad) * m->forwardVel;
}

void NotifyLanded(MarioState* m, float newFloorY) {
    m->isGrounded = true;
    m->floorHeight = newFloorY;
    m->vel[1] = 0.0f;
    s_landTimer = 0;
    if (m->action == ACT_DIVE) {
        SetAction(m, ACT_DIVE_SLIDE);
    } else if (m->action == ACT_GROUND_POUND) {
        SetAction(m, ACT_GROUND_POUND_LAND);
        m->forwardVel = 0.0f;
    } else {
        SetAction(m, ACT_IDLE);
    }
}

} // namespace SM64
