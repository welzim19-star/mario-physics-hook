import os
import re

file_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Do NOT zero left stick for Elden Ring in Detour_XInputGetState
old_detour = """static DWORD WINAPI Detour_XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) {
    if (!Original_XInputGetState) return ERROR_DEVICE_NOT_CONNECTED;
    DWORD res = Original_XInputGetState(dwUserIndex, pState);
    if (res == ERROR_SUCCESS && pState && dwUserIndex == 0) {
        g_RawPad = *pState;
        g_PadCaptured = true;

        if (g_PlayerIns.load(std::memory_order_relaxed) != 0) {
            // Left stick belongs to Mario: zero it out for Elden Ring so Souls controller stays idle
            pState->Gamepad.sThumbLX = 0;
            pState->Gamepad.sThumbLY = 0;
        }
    }
    return res;
}"""

new_detour = """static DWORD WINAPI Detour_XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) {
    if (!Original_XInputGetState) return ERROR_DEVICE_NOT_CONNECTED;
    DWORD res = Original_XInputGetState(dwUserIndex, pState);
    if (res == ERROR_SUCCESS && pState && dwUserIndex == 0) {
        g_RawPad = *pState;
        g_PadCaptured = true;
        // Native Elden Ring Havok handles character movement with the left stick smoothly
    }
    return res;
}"""

# Normalise line endings for matching
content_crlf = content.replace("\r\n", "\n")
old_detour_norm = old_detour.replace("\r\n", "\n")
new_detour_norm = new_detour.replace("\r\n", "\n")

if old_detour_norm in content_crlf:
    content_crlf = content_crlf.replace(old_detour_norm, new_detour_norm)
    print("Hook XInputGetState successfully updated (no zeroing of left stick).")
else:
    print("Warning: old_detour not found!")

# 2. Replace the tick logic inside while (accum >= SM64_DT) and outer loop
old_tick_block = """        while (accum >= SM64_DT) {
            accum -= SM64_DT;
            prevSmY = currSmY;

            // Measure horizontal movement speed in Elden Ring
            float horizDist = std::sqrt((erPos.x - lastErPos.x)*(erPos.x - lastErPos.x) + (erPos.z - lastErPos.z)*(erPos.z - lastErPos.z));
            lastErPos = erPos;
            bool movingInEr = (horizDist > 0.015f) || (slen > 0.1f);

            // Sync Mario's facing with the character's facing in Elden Ring
            sm64_set_mario_faceangle(marioId, erFaceAngle);

            bool attackPressed = s_AttackLatched || rawAttack;
            s_AttackLatched = false;
            bool jumpPressed = s_JumpLatched || rawJump;
            s_JumpLatched = false;
            bool dodgePressed = s_DodgeLatched || rawDodge;
            s_DodgeLatched = false;
            bool zPressed = rawZ; // Held, not latched, so releasing LT lets Mario stand up instantly!

            bool isAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);

            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;

            if (dodgePressed && movingInEr && !isAirborne) {
                // Dodge / B while moving = Mario's signature Dive & Rollout!
                btnB = 1;
            } else if (attackPressed) {
                // Pulse 0 then 1 for responsive 3-hit punch combo
                if (inPunchAction && s_LastSentB == 1) {
                    btnB = 0;
                } else {
                    btnB = 1;
                }
            }
            s_LastSentB = btnB;

            uint8_t btnA = jumpPressed ? 1 : 0;
            uint8_t btnZ = zPressed ? 1 : 0;

            inputs.camLookX = -dir.x;
            inputs.camLookZ = dir.z;
            inputs.stickX = 0.0f;

            if (dodgePressed && movingInEr && !isAirborne) {
                inputs.stickY = -1.0f; // full forward speed for Dive
            } else if (btnB && !isAirborne) {
                // Attack on ground: standing still or slight stick guarantees Punch combo instead of Dive
                inputs.stickY = movingInEr ? -0.3f : 0.0f;
            } else if (inPunchAction && !isAirborne) {
                // In punch animation: zero out stick so combo connects seamlessly
                inputs.stickY = 0.0f;
            } else {
                inputs.stickY = movingInEr ? -1.0f : 0.0f;
            }

            inputs.buttonA = btnA;
            inputs.buttonB = btnB;
            inputs.buttonZ = btnZ;

            sm64_mario_tick(marioId, &inputs, &state, &geoBufs);
            TickSM64Audio();

            int cnt = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);
            int rightHandTris = 0;
            for (uint16_t t = 0; t < geoBufs.numTrianglesUsed; ++t) {
                if (triParts[t] == RIGHT_HAND_PART) rightHandTris++;
            }
            bool peace = (rightHandTris > FIST_TRIANGLES);
            uint8_t eye = ComputeEyeCell(geoUv.data(), geoBufs.numTrianglesUsed);
            prevPose = currPose;
            currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, peace);

            // Elden Ring Havok owns horizontal base movement: keep SM64 X/Z at the origin, height is tracked for jumps/somersaults
            currSmY = std::max(0.0f, state.position[1]);
            sm64_set_mario_position(marioId, 0.0f, currSmY, 0.0f);
            state.position[0] = 0.0f;
            state.position[2] = 0.0f;

            // Combat damage against enemies and bosses
            DealMarioCombatDamage(worldChrManPtr, playerIns, erPos, state);
        }

        // Keep stamina full so player can jump and attack infinitely with Mario
        int32_t maxSp = *(int32_t*)(dataMod + 0x158);
        if (maxSp > 0) *(int32_t*)(dataMod + 0x154) = maxSp;

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        float smoothSmY = prevSmY + (currSmY - prevSmY) * alpha;

        bool airborne = (state.action & 0x00000800) != 0;
        bool isLongJump = (state.action == 0x03000888);
        bool isDive = (state.action == 0x01880888 || state.action == 0x0188088A);
        float extraLiftY = 0.0f;

        if (!airborne) {
            groundErY = erPos.y;
        } else {
            float erRise = std::max(0.0f, erPos.y - groundErY);
            // SM64 jump height: normal jump ~1.8m, double jump ~2.6m, triple jump / somersault ~3.8m
            float smRise = std::clamp(smoothSmY * SCALE_ER, 0.0f, 4.2f);
            extraLiftY = std::max(0.0f, smRise - erRise);

            // N64 Acrobatics Mechanics Enhancement:
            // 1. Long Jump & Dive horizontal forward propulsion:
            if (isLongJump || isDive) {
                float forwardSpeed = isLongJump ? 10.0f : 7.0f; // m/s
                *(float*)(physMod + 0x70) += dir.x * (forwardSpeed * dt);
                *(float*)(physMod + 0x78) += dir.z * (forwardSpeed * dt);
                *(uint8_t*)(physMod + 0x91) = 1;
            }

            // 2. Vertical air lift: Mario's capsule also lifts off the ground with extraLiftY, but NEVER drops below groundErY!
            if (extraLiftY > 0.05f) {
                *(float*)(physMod + 0x74) = groundErY + erRise + extraLiftY;
                *(uint8_t*)(physMod + 0x91) = 1;
                *(uint8_t*)(physMod + 0x1d5) = 1; // disable ER gravity during peak air acrobatics
            }
        }

        // When touching ground, restore native Havok collision
        if (!airborne) {
            *(uint8_t*)(physMod + 0x1d5) = 0;
            *(uint8_t*)(physMod + 0x1d0) = 0;
            *(uint8_t*)(physMod + 0x1d1) = 1;
            *(uint8_t*)(physMod + 0x92) = 1;
            *(uint8_t*)(physMod + 0x93) = 1;
        }"""

new_tick_block = """        while (accum >= SM64_DT) {
            accum -= SM64_DT;
            prevSmY = currSmY;

            // Measure horizontal movement speed in Elden Ring
            float horizDist = std::sqrt((erPos.x - lastErPos.x)*(erPos.x - lastErPos.x) + (erPos.z - lastErPos.z)*(erPos.z - lastErPos.z));
            lastErPos = erPos;
            bool movingInEr = (horizDist > 0.015f) || (slen > 0.15f);

            // Sync Mario's facing with the character's facing in Elden Ring
            sm64_set_mario_faceangle(marioId, erFaceAngle);

            bool attackPressed = s_AttackLatched || rawAttack;
            s_AttackLatched = false;
            bool jumpPressed = s_JumpLatched || rawJump;
            s_JumpLatched = false;
            bool dodgePressed = s_DodgeLatched || rawDodge;
            s_DodgeLatched = false;
            bool zPressed = rawZ;

            // 1. IMMORTALITY & ANTI-FREEZE: Keep Mario full health & immortal so he NEVER dies from fall damage
            sm64_set_mario_health(marioId, 0x0880);

            // Detect action categories
            bool isAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);
            bool isSlideAction = (state.action == 0x00880456 /* ACT_DIVE_SLIDE */ ||
                                  state.action == 0x00000386 /* ACT_STOMACH_SLIDE_STOP */ ||
                                  state.action == 0x04808459 /* ACT_CROUCH_SLIDE */ ||
                                  state.action == 0x0080045A /* ACT_SLIDE_KICK_SLIDE */ ||
                                  state.action == 0x00840452 /* ACT_BUTT_SLIDE */ ||
                                  state.action == 0x0C00023E /* ACT_BUTT_SLIDE_STOP */ ||
                                  state.action == 0x0800023B /* ACT_LONG_JUMP_LAND_STOP */ ||
                                  state.action == 0x0800023A /* ACT_TRIPLE_JUMP_LAND_STOP */ ||
                                  state.action == 0x0800022F /* ACT_BACKFLIP_LAND_STOP */);
            bool isCrouchAction = (state.action == 0x0C008220 /* ACT_CROUCHING */ ||
                                   state.action == 0x0C008221 /* ACT_START_CROUCHING */ ||
                                   state.action == 0x04000443 /* ACT_START_CRAWLING */ ||
                                   state.action == 0x04000444 /* ACT_CRAWLING */);

            // Never let death or cutscene actions freeze Mario
            if ((state.action & 0x000001C0) == 0x00000100 /* ACT_GROUP_CUTSCENE: death */ || state.health < 0x100) {
                sm64_set_mario_action(marioId, 0x0C400201 /* ACT_IDLE */);
                sm64_set_mario_health(marioId, 0x0880);
            }

            // 2. CROUCH RELEASE: When player releases Z, Mario immediately stands up
            if (!zPressed && isCrouchAction) {
                sm64_set_mario_action(marioId, 0x0C400201 /* ACT_IDLE */);
            }

            // 3. DIVE SLIDE ROLLOUT: If in dive slide and Jump (A) is pressed, rollout back to feet!
            if ((state.action == 0x00880456 /* ACT_DIVE_SLIDE */ || state.action == 0x00000386 /* ACT_STOMACH_SLIDE_STOP */) && jumpPressed) {
                sm64_set_mario_action(marioId, 0x010008A6 /* ACT_FORWARD_ROLLOUT */);
                jumpPressed = false;
            }

            // Track same action ticks for anti-freeze watchdog
            static uint32_t s_LastAction = 0;
            static int s_SameActionTicks = 0;
            if (state.action == s_LastAction) {
                s_SameActionTicks++;
            } else {
                s_LastAction = state.action;
                s_SameActionTicks = 0;
            }

            // If Mario stays in a slide/landing pose for > 15 ticks (~0.5s) while moving, stand up!
            if (movingInEr && isSlideAction && s_SameActionTicks > 15) {
                sm64_set_mario_action(marioId, 0x04000440 /* ACT_WALKING */);
                s_SameActionTicks = 0;
            }

            // General watchdog: if Mario stays in ANY non-walking action for > 30 ticks while moving in ER, resume walking!
            if (movingInEr && s_SameActionTicks > 30 && state.action != 0x04000440 /* ACT_WALKING */ && state.action != 0x0C400201 /* ACT_IDLE */) {
                sm64_set_mario_action(marioId, 0x04000440 /* ACT_WALKING */);
                s_SameActionTicks = 0;
            }

            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;

            if (dodgePressed && movingInEr && !isAirborne) {
                // Dodge / B while moving = Mario's signature Dive!
                btnB = 1;
            } else if (attackPressed) {
                // Pulse 0 then 1 for responsive 3-hit punch combo
                if (inPunchAction && s_LastSentB == 1) {
                    btnB = 0;
                } else {
                    btnB = 1;
                }
            }
            s_LastSentB = btnB;

            uint8_t btnA = jumpPressed ? 1 : 0;
            uint8_t btnZ = zPressed ? 1 : 0;

            inputs.camLookX = -dir.x;
            inputs.camLookZ = dir.z;

            // Feed stick inputs smoothly:
            if (isSlideAction) {
                // In slide: zero out stick so SM64 decelerates naturally and transitions to standing
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            } else if (inPunchAction && !isAirborne) {
                // In punch combo: keep stick zeroed so punch combo connects cleanly without diving
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            } else if (dodgePressed && movingInEr && !isAirborne) {
                // Dive trigger: full forward stick guarantees Dive instead of punch
                inputs.stickX = 0.0f;
                inputs.stickY = -1.0f;
            } else if (btnB && !isAirborne) {
                // Ground attack: neutral or slight stick guarantees Punch
                inputs.stickX = 0.0f;
                inputs.stickY = movingInEr ? -0.3f : 0.0f;
            } else if (movingInEr) {
                // Player is moving: pass analog stick or forward if moving
                if (slen > 0.15f) {
                    inputs.stickX = stickX;
                    inputs.stickY = stickY;
                } else {
                    inputs.stickX = 0.0f;
                    inputs.stickY = -1.0f; // full forward run
                }
            } else {
                // Idle / standing still
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            }

            inputs.buttonA = btnA;
            inputs.buttonB = btnB;
            inputs.buttonZ = btnZ;

            sm64_mario_tick(marioId, &inputs, &state, &geoBufs);
            TickSM64Audio();

            int cnt = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);
            int rightHandTris = 0;
            for (uint16_t t = 0; t < geoBufs.numTrianglesUsed; ++t) {
                if (triParts[t] == RIGHT_HAND_PART) rightHandTris++;
            }
            bool peace = (rightHandTris > FIST_TRIANGLES);
            uint8_t eye = ComputeEyeCell(geoUv.data(), geoBufs.numTrianglesUsed);
            prevPose = currPose;
            currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, peace);

            // Elden Ring Havok owns horizontal base movement: keep SM64 X/Z at the origin, height is tracked for jumps/somersaults
            currSmY = std::max(0.0f, state.position[1]);
            sm64_set_mario_position(marioId, 0.0f, currSmY, 0.0f);
            state.position[0] = 0.0f;
            state.position[2] = 0.0f;

            // Combat damage against enemies and bosses
            DealMarioCombatDamage(worldChrManPtr, playerIns, erPos, state);
        }

        // Keep stamina full so player can jump and attack infinitely with Mario
        int32_t maxSp = *(int32_t*)(dataMod + 0x158);
        if (maxSp > 0) *(int32_t*)(dataMod + 0x154) = maxSp;

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        float smoothSmY = prevSmY + (currSmY - prevSmY) * alpha;

        bool airborne = (state.action & 0x00000800) != 0;
        float extraLiftY = 0.0f;

        if (airborne) {
            // Visual height lift in character space for acrobatic jumps, somersaults and flips
            extraLiftY = std::clamp(smoothSmY * SCALE_ER, 0.0f, 2.5f);
        }

        // Native Elden Ring Havok handles all capsule physics, terrain, ground and walls:
        // No direct writes to physical memory coords: Havok ensures 100% collision integrity!"""

old_tick_norm = old_tick_block.replace("\r\n", "\n")
new_tick_norm = new_tick_block.replace("\r\n", "\n")

if old_tick_norm in content_crlf:
    content_crlf = content_crlf.replace(old_tick_norm, new_tick_norm)
    print("Tick block successfully updated with anti-freeze and native Havok physics.")
else:
    print("Warning: old_tick_block not found!")

# Convert back to Windows CRLF
content_final = content_crlf.replace("\n", "\r\n")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content_final)

print("Patch applied to dll_main.cpp.")
