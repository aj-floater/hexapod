#include "SceneModel.h"

#include <algorithm>

#include <Magnum/Math/Functions.h>

using namespace Magnum::Math::Literals;

namespace hexapod::simulation {

namespace {

Magnum::Range3D transformBounds(const Magnum::Range3D& bounds, const Magnum::Matrix4& transform) {
    Magnum::Range3D result;
    bool initialized = false;

    for(Magnum::UnsignedInt mask = 0; mask != 8; ++mask) {
        const Magnum::Vector3 corner{
            (mask & 1) ? bounds.max().x() : bounds.min().x(),
            (mask & 2) ? bounds.max().y() : bounds.min().y(),
            (mask & 4) ? bounds.max().z() : bounds.min().z()};
        const Magnum::Vector3 worldCorner = transform.transformPoint(corner);
        if(!initialized) {
            result = Magnum::Range3D::fromSize(worldCorner, {});
            initialized = true;
        } else {
            result = Magnum::Math::join(result, worldCorner);
        }
    }

    return result;
}

Magnum::Matrix4 rigidTransform(const Magnum::Matrix4& transform) {
    return Magnum::Matrix4::from(transform.rotation(), transform.translation());
}

}

Magnum::Matrix4 Transform::matrix() const {
    return Magnum::Matrix4::translation(translation)*
        Magnum::Matrix4::rotationZ(Magnum::Deg{rotationDegrees.z()})*
        Magnum::Matrix4::rotationY(Magnum::Deg{rotationDegrees.y()})*
        Magnum::Matrix4::rotationX(Magnum::Deg{rotationDegrees.x()})*
        Magnum::Matrix4::scaling(scale);
}

Magnum::Range3D SceneEntity::localBounds() const {
    switch(primitive) {
        case PrimitiveKind::Cylinder:
        case PrimitiveKind::Sphere:
            return {{-1.0f, -1.0f, -1.0f}, {1.0f, 1.0f, 1.0f}};
        case PrimitiveKind::Cube:
        default:
            return {{-0.5f, -0.5f, -0.5f}, {0.5f, 0.5f, 0.5f}};
    }
}

SceneModel::SceneModel() {
    createDefaultScene();
}

FrameState SceneModel::frameState() const {
    return FrameState{_entities};
}

SceneEntity* SceneModel::findEntity(const Magnum::Int id) {
    const auto it = std::find_if(_entities.begin(), _entities.end(), [id](const SceneEntity& entity) {
        return Magnum::Int(entity.id) == id;
    });
    return it == _entities.end() ? nullptr : &*it;
}

const SceneEntity* SceneModel::findEntity(const Magnum::Int id) const {
    const auto it = std::find_if(_entities.begin(), _entities.end(), [id](const SceneEntity& entity) {
        return Magnum::Int(entity.id) == id;
    });
    return it == _entities.end() ? nullptr : &*it;
}

std::vector<Magnum::Int> SceneModel::childIds(const Magnum::Int parentId) const {
    std::vector<Magnum::Int> children;
    for(const SceneEntity& entity: _entities) {
        if(entity.parentId == parentId)
            children.push_back(Magnum::Int(entity.id));
    }
    return children;
}

Magnum::Matrix4 SceneModel::worldTransform(const Magnum::Int id) const {
    const SceneEntity* entity = findEntity(id);
    if(!entity) return Magnum::Matrix4{Magnum::Math::IdentityInit};

    if(entity->parentId < 0) return entity->localTransform.matrix();
    return rigidTransform(worldTransform(entity->parentId))*entity->localTransform.matrix();
}

Magnum::Range3D SceneModel::worldBounds(const Magnum::Int id) const {
    const SceneEntity* entity = findEntity(id);
    if(!entity) return Magnum::Range3D{};

    return transformBounds(entity->localBounds(), worldTransform(id));
}

std::optional<Magnum::Range3D> SceneModel::visibleBounds() const {
    std::optional<Magnum::Range3D> bounds;

    for(const SceneEntity& entity: _entities) {
        if(!entity.visible) continue;

        const Magnum::Range3D entityBounds = worldBounds(Magnum::Int(entity.id));
        if(bounds)
            *bounds = Magnum::Math::join(*bounds, entityBounds);
        else
            bounds = entityBounds;
    }

    return bounds;
}

std::optional<SceneRayHit> SceneModel::raycast(const Ray3D& ray) const {
    std::optional<SceneRayHit> bestHit;

    for(const SceneEntity& entity: _entities) {
        if(!entity.visible) continue;

        const Magnum::Matrix4 world = worldTransform(Magnum::Int(entity.id));
        const Magnum::Matrix4 inverseWorld = world.inverted();
        const Ray3D localRay{
            inverseWorld.transformPoint(ray.origin),
            inverseWorld.transformVector(ray.direction).normalized()};

        Magnum::Float localHitDistance{};
        if(!intersectAabb(localRay, entity.localBounds(), localHitDistance)) continue;

        const Magnum::Vector3 localHitPoint = localRay.origin + localRay.direction*localHitDistance;
        const Magnum::Vector3 worldHitPoint = world.transformPoint(localHitPoint);
        const Magnum::Float worldDistance = (worldHitPoint - ray.origin).length();

        if(bestHit && worldDistance >= bestHit->distance) continue;
        bestHit = SceneRayHit{Magnum::Int(entity.id), worldDistance, worldHitPoint};
    }

    return bestHit;
}

void SceneModel::createDefaultScene() {
    _entities = {
        SceneEntity{
            1,
            -1,
            "Anchor",
            PrimitiveKind::Cube,
            0x293241_rgbf,
            Transform{{0.0f, -0.4f, 0.0f}, {}, {2.8f, 0.4f, 2.8f}},
            true},
        SceneEntity{
            2,
            1,
            "Joint",
            PrimitiveKind::Cylinder,
            0xd97745_rgbf,
            Transform{{0.0f, 0.7f, 0.0f}, {0.0f, 0.0f, 90.0f}, {0.24f, 0.24f, 0.24f}},
            true},
        SceneEntity{
            3,
            2,
            "Link",
            PrimitiveKind::Cube,
            0xf2a65a_rgbf,
            Transform{{1.2f, 0.0f, 0.0f}, {0.0f, 0.0f, 18.0f}, {2.4f, 0.28f, 0.42f}},
            true},
        SceneEntity{
            4,
            3,
            "End Effector",
            PrimitiveKind::Sphere,
            0x98c1d9_rgbf,
            Transform{{1.2f, 0.0f, 0.0f}, {}, {0.26f, 0.26f, 0.26f}},
            true},
        SceneEntity{
            5,
            -1,
            "Reference Block",
            PrimitiveKind::Cube,
            0x4f5d75_rgbf,
            Transform{{-2.2f, 0.35f, -1.5f}, {0.0f, 25.0f, 0.0f}, {0.8f, 0.8f, 0.8f}},
            true}
    };
}

}
