#pragma once

#include <string>
#include <vector>

#include <Magnum/Magnum.h>
#include <Magnum/Math/Color.h>
#include <Magnum/Math/Matrix4.h>
#include <Magnum/Math/Range.h>
#include <Magnum/Math/Vector2.h>
#include <Magnum/Math/Vector3.h>

namespace hexapod::simulation {

using EntityId = Magnum::UnsignedInt;

enum class PrimitiveKind: Magnum::UnsignedByte {
    Cube,
    Cylinder,
    Sphere
};

enum class GizmoOperation: Magnum::UnsignedByte {
    Translate,
    Rotate
};

enum class GizmoSpace: Magnum::UnsignedByte {
    Local,
    World
};

struct Transform {
    Magnum::Vector3 translation{};
    Magnum::Vector3 rotationDegrees{};
    Magnum::Vector3 scale{1.0f};

    Magnum::Matrix4 matrix() const;
};

struct SceneEntity {
    EntityId id{};
    Magnum::Int parentId{-1};
    std::string label;
    PrimitiveKind primitive{PrimitiveKind::Cube};
    Magnum::Color4 color{1.0f};
    Transform localTransform{};
    bool visible{true};

    Magnum::Range3D localBounds() const;
};

struct SelectionState {
    Magnum::Int selectedId{-1};
    Magnum::Int hoveredId{-1};
    GizmoOperation operation{GizmoOperation::Translate};
    GizmoSpace space{GizmoSpace::Local};
};

struct PanelVisibility {
    bool hierarchy{true};
    bool inspector{true};
    bool log{true};
};

struct EditorPreferences {
    bool translateSnapEnabled{true};
    Magnum::Vector3 translateSnap{0.25f};
    bool rotateSnapEnabled{true};
    Magnum::Float rotateSnapDegrees{15.0f};
    bool showGrid{true};
    bool showBounds{true};
    bool showAxes{true};
    bool showDemoWindow{false};
};

struct WorkspaceLayoutState {
    PanelVisibility panels{};
    bool defaultLayoutPending{true};
};

struct SceneRayHit {
    Magnum::Int entityId{-1};
    Magnum::Float distance{};
    Magnum::Vector3 worldPosition{};
};

struct FrameState {
    std::vector<SceneEntity> entities;
};

class SceneSource {
    public:
        virtual ~SceneSource() = default;
        virtual FrameState frameState() const = 0;
};

}
