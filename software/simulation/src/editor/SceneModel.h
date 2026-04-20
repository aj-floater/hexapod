#pragma once

#include <optional>
#include <vector>

#include "EditorTypes.h"
#include "MathUtils.h"

namespace hexapod::simulation {

class SceneModel: public SceneSource {
    public:
        SceneModel();

        FrameState frameState() const override;

        const std::vector<SceneEntity>& entities() const { return _entities; }
        std::vector<SceneEntity>& entities() { return _entities; }

        SceneEntity* findEntity(Magnum::Int id);
        const SceneEntity* findEntity(Magnum::Int id) const;

        std::vector<Magnum::Int> childIds(Magnum::Int parentId) const;
        Magnum::Matrix4 worldTransform(Magnum::Int id) const;
        Magnum::Range3D worldBounds(Magnum::Int id) const;
        std::optional<Magnum::Range3D> visibleBounds() const;
        std::optional<SceneRayHit> raycast(const Ray3D& ray) const;

    private:
        void createDefaultScene();

        std::vector<SceneEntity> _entities;
};

}
