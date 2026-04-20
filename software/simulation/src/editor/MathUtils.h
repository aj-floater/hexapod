#pragma once

#include <algorithm>
#include <limits>

#include <Magnum/Math/Matrix4.h>
#include <Magnum/Math/Vector2.h>
#include <Magnum/Math/Vector3.h>
#include <Magnum/Math/Vector4.h>

#include "EditorTypes.h"

namespace hexapod::simulation {

constexpr Magnum::Deg ViewportVerticalFov = Magnum::Deg{45.0f};
constexpr Magnum::Float CameraMinDistance = 1.5f;
constexpr Magnum::Float CameraMaxDistance = 40.0f;

struct Ray3D {
    Magnum::Vector3 origin;
    Magnum::Vector3 direction;
};

inline Magnum::Float framingDistanceForRadius(const Magnum::Float radius,
                                              const Magnum::Float aspectRatio,
                                              const Magnum::Deg verticalFov = ViewportVerticalFov) {
    const Magnum::Float safeRadius = Magnum::Math::max(radius, 0.05f);
    const Magnum::Rad verticalHalf = Magnum::Rad{verticalFov}*0.5f;
    const Magnum::Rad horizontalHalf =
        Magnum::Math::atan(Magnum::Math::tan(verticalHalf)*Magnum::Math::max(aspectRatio, 0.01f));
    const Magnum::Rad limitingHalfAngle = Magnum::Math::min(verticalHalf, horizontalHalf);
    return safeRadius/Magnum::Math::sin(limitingHalfAngle);
}

inline Ray3D screenPointToRay(const Magnum::Vector2 localPosition,
                              const Magnum::Vector2 viewportSize,
                              const Magnum::Matrix4& view,
                              const Magnum::Matrix4& projection) {
    const Magnum::Vector2 ndc{
        2.0f*localPosition.x()/viewportSize.x() - 1.0f,
        1.0f - 2.0f*localPosition.y()/viewportSize.y()};

    const Magnum::Matrix4 inverse = (projection*view).inverted();

    const Magnum::Vector4 nearClip{ndc.x(), ndc.y(), -1.0f, 1.0f};
    const Magnum::Vector4 farClip{ndc.x(), ndc.y(), 1.0f, 1.0f};

    const Magnum::Vector4 nearWorld4 = inverse*nearClip;
    const Magnum::Vector4 farWorld4 = inverse*farClip;

    const Magnum::Vector3 nearWorld = nearWorld4.xyz()/nearWorld4.w();
    const Magnum::Vector3 farWorld = farWorld4.xyz()/farWorld4.w();
    return {nearWorld, (farWorld - nearWorld).normalized()};
}

inline bool intersectAabb(const Ray3D& ray,
                          const Magnum::Range3D& bounds,
                          Magnum::Float& hitDistance) {
    Magnum::Float tMin = 0.0f;
    Magnum::Float tMax = std::numeric_limits<Magnum::Float>::max();

    for(Magnum::Int axis = 0; axis != 3; ++axis) {
        const Magnum::Float origin = ray.origin[axis];
        const Magnum::Float direction = ray.direction[axis];
        const Magnum::Float minValue = bounds.min()[axis];
        const Magnum::Float maxValue = bounds.max()[axis];

        if(std::abs(direction) < 1.0e-5f) {
            if(origin < minValue || origin > maxValue) return false;
            continue;
        }

        Magnum::Float t1 = (minValue - origin)/direction;
        Magnum::Float t2 = (maxValue - origin)/direction;
        if(t1 > t2) std::swap(t1, t2);

        tMin = std::max(tMin, t1);
        tMax = std::min(tMax, t2);
        if(tMin > tMax) return false;
    }

    hitDistance = tMin;
    return true;
}

}
