/*
    This file is part of Magnum.

    Original authors — credit is appreciated but not required:

        2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019,
        2020, 2021, 2022, 2023, 2024, 2025, 2026
             — Vladimír Vondruš <mosra@centrum.cz>
        2020 — Nghia Truong <nghiatruong.vn@gmail.com>

    This is free and unencumbered software released into the public domain.

    Anyone is free to copy, modify, publish, use, compile, sell, or distribute
    this software, either in source code form or as a compiled binary, for any
    purpose, commercial or non-commercial, and by any means.

    In jurisdictions that recognize copyright laws, the author or authors of
    this software dedicate any and all copyright interest in the software to
    the public domain. We make this dedication for the benefit of the public
    at large and to the detriment of our heirs and successors. We intend this
    dedication to be an overt act of relinquishment in perpetuity of all
    present and future rights to this software under copyright law.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
    THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
    IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/

#include "ArcBall.h"

#include <cmath>

#include <Corrade/Utility/Assert.h>

namespace Magnum { namespace Examples {

namespace {

constexpr Float MinViewDistance = 0.25f;
constexpr Float MaxViewDistance = 100.0f;
constexpr Rad RotationPerNdc = Deg{90.0f};
constexpr Rad PitchLimit = Deg{89.0f};

Vector3 referenceForward(const Vector3& worldUp) {
    const Vector3 referenceAxis =
        Math::abs(Math::dot(worldUp, Vector3::zAxis())) < 0.99f ?
        Vector3::zAxis() : Vector3::xAxis();
    const Vector3 right = Math::cross(referenceAxis, worldUp).normalized();
    return Math::cross(worldUp, right).normalized();
}

struct TurntableBasis {
    Vector3 forward;
    Vector3 right;
    Vector3 up;
};

TurntableBasis basisFromAngles(const Vector3& worldUp, const Rad yaw, const Rad pitch) {
    const Vector3 flatForward =
        Quaternion::rotation(yaw, worldUp).transformVector(referenceForward(worldUp)).normalized();
    const Vector3 right = Math::cross(flatForward, worldUp).normalized();
    const Vector3 forward = Quaternion::rotation(pitch, right).transformVector(flatForward).normalized();
    const Vector3 up = Math::cross(right, forward).normalized();
    return {forward, right, up};
}

Rad clampPitch(const Rad pitch) {
    return Rad{Math::clamp(Float(pitch), -Float(PitchLimit), Float(PitchLimit))};
}

Float shortestAngleDelta(const Float from, const Float to) {
    constexpr Float Tau = 6.28318530718f;
    constexpr Float Pi = 3.14159265359f;

    Float delta = to - from;
    while(delta > Pi) delta -= Tau;
    while(delta < -Pi) delta += Tau;
    return delta;
}

struct TurntableState {
    Rad yaw;
    Rad pitch;
    Float distance;
};

TurntableState stateFromView(const Vector3& eye,
                            const Vector3& viewCenter,
                            const Vector3& worldUp) {
    const Vector3 offset = eye - viewCenter;
    const Float distance = Math::max(offset.length(), MinViewDistance);
    const Vector3 forward =
        offset.length() > 1.0e-6f ?
        (viewCenter - eye).normalized() :
        referenceForward(worldUp);
    const Float vertical = Math::clamp(Math::dot(forward, worldUp), -1.0f, 1.0f);
    const Rad pitch = clampPitch(Rad{std::asin(vertical)});

    Vector3 flatForward = forward - worldUp*vertical;
    if(Math::dot(flatForward, flatForward) < 1.0e-8f)
        flatForward = referenceForward(worldUp);
    else
        flatForward = flatForward.normalized();

    const Vector3 baseForward = referenceForward(worldUp);
    const Float sinYaw = Math::dot(Math::cross(baseForward, flatForward), worldUp);
    const Float cosYaw = Math::dot(baseForward, flatForward);
    return {Rad{std::atan2(sinYaw, cosYaw)}, pitch, distance};
}

}

ArcBall::ArcBall(const Vector3& eye, const Vector3& viewCenter,
    const Vector3& upDir, Deg fov, const Vector2i& windowSize):
    _fov{fov}, _windowSize{windowSize}
{
    setViewParameters(eye, viewCenter, upDir);
}

void ArcBall::setViewParameters(const Vector3& eye, const Vector3& viewCenter,
    const Vector3& upDir)
{
    _worldUp = upDir.normalized();
    const TurntableState state = stateFromView(eye, viewCenter, _worldUp);

    _targetCenter = viewCenter;
    _targetDistance = state.distance;
    _targetYaw = state.yaw;
    _targetPitch = state.pitch;

    _centerT0 = _currentCenter = _targetCenter;
    _distanceT0 = _currentDistance = _targetDistance;
    _yawT0 = _currentYaw = _targetYaw;
    _pitchT0 = _currentPitch = _targetPitch;

    updateInternalTransformations();
}

void ArcBall::reset() {
    _targetCenter = _centerT0;
    _targetDistance = _distanceT0;
    _targetYaw = _yawT0;
    _targetPitch = _pitchT0;
}

void ArcBall::setLagging(const Float lagging) {
    CORRADE_INTERNAL_ASSERT(lagging >= 0.0f && lagging < 1.0f);
    _lagging = lagging;
}

void ArcBall::initTransformation(const Vector2& pointerPosition) {
    _prevPointerPositionNdc = screenCoordToNdc(pointerPosition);
}

void ArcBall::rotate(const Vector2& pointerPosition) {
    const Vector2 pointerPositionNdc = screenCoordToNdc(pointerPosition);
    const Vector2 delta = pointerPositionNdc - _prevPointerPositionNdc;
    _prevPointerPositionNdc = pointerPositionNdc;

    _targetYaw = Rad{Float(_targetYaw) - delta.x()*Float(RotationPerNdc)};
    _targetPitch = clampPitch(
        Rad{Float(_targetPitch) + delta.y()*Float(RotationPerNdc)});
}

void ArcBall::translate(const Vector2& pointerPosition) {
    const Vector2 mousePosNdc = screenCoordToNdc(pointerPosition);
    const Vector2 translationNdc = mousePosNdc - _prevPointerPositionNdc;
    _prevPointerPositionNdc = mousePosNdc;
    translateDelta(translationNdc);
}

void ArcBall::translateDelta(const Vector2& translationNdc) {
    /* Half size of the screen viewport at the view center and perpendicular
       with the viewDir */
    const Float hh = _targetDistance*Math::tan(_fov*0.5f);
    const Float hw = hh*Vector2{_windowSize}.aspectRatio();
    const TurntableBasis basis = basisFromAngles(_worldUp, _targetYaw, _targetPitch);

    _targetCenter +=
        (-basis.right*translationNdc.x()*hw) +
        (basis.up*translationNdc.y()*hh);
}

void ArcBall::zoom(const Float delta) {
    _targetDistance = Math::clamp(_targetDistance - delta, MinViewDistance, MaxViewDistance);
}

bool ArcBall::updateTransformation() {
    const Vector3 diffViewCenter = _targetCenter - _currentCenter;
    const Float diffYaw = shortestAngleDelta(Float(_currentYaw), Float(_targetYaw));
    const Float diffPitch = Float(_targetPitch) - Float(_currentPitch);
    const Float diffZooming = _targetDistance - _currentDistance;

    const Float dViewCenter = Math::dot(diffViewCenter, diffViewCenter);
    const Float dRotation = diffYaw*diffYaw + diffPitch*diffPitch;
    const Float dZooming = diffZooming * diffZooming;

    /* Nothing change */
    if(dViewCenter < 1.0e-10f &&
       dRotation < 1.0e-10f &&
       dZooming < 1.0e-10f) {
        return false;
    }

    /* Nearly done: just jump directly to the target */
    if(dViewCenter < 1.0e-6f &&
       dRotation < 1.0e-6f &&
       dZooming < 1.0e-6f) {
        _currentCenter = _targetCenter;
        _currentYaw = _targetYaw;
        _currentPitch = _targetPitch;
        _currentDistance = _targetDistance;

    /* Interpolate between the current transformation and the target
       transformation */
    } else {
        const Float t = 1 - _lagging;
        _currentCenter = Math::lerp(_currentCenter, _targetCenter, t);
        _currentDistance = Math::lerp(_currentDistance, _targetDistance, t);
        _currentYaw = Rad{
            Float(_currentYaw) + shortestAngleDelta(Float(_currentYaw), Float(_targetYaw))*t};
        _currentPitch = Rad{
            Math::lerp(Float(_currentPitch), Float(_targetPitch), t)};
    }

    updateInternalTransformations();
    return true;
}

void ArcBall::updateInternalTransformations() {
    const TurntableBasis basis = basisFromAngles(_worldUp, _currentYaw, _currentPitch);
    const Vector3 eye = _currentCenter - basis.forward*_currentDistance;
    _inverseViewMatrix = Matrix4::lookAt(eye, _currentCenter, basis.up);
    _viewMatrix = _inverseViewMatrix.invertedRigid();

    _view = DualQuaternion::fromMatrix(_viewMatrix);
    _inverseView = DualQuaternion::fromMatrix(_inverseViewMatrix);
}

Vector2 ArcBall::screenCoordToNdc(const Vector2& pointerPosition) const {
    return Vector2::yScale(-1.0f)*
        (pointerPosition*2.0f/Vector2{_windowSize} - Vector2{1.0f});
}

}}
