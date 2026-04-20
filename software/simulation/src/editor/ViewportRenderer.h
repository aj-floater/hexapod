#pragma once

#include <Magnum/GL/Framebuffer.h>
#include <Magnum/GL/Mesh.h>
#include <Magnum/GL/Renderbuffer.h>
#include <Magnum/GL/Texture.h>
#include <Magnum/Shaders/FlatGL.h>
#include <Magnum/Shaders/PhongGL.h>
#include <Magnum/Shaders/VertexColorGL.h>

#include "EditorTypes.h"
#include "SceneModel.h"

namespace hexapod::simulation {

class ViewportRenderer {
    public:
        ViewportRenderer();

        void ensureSize(const Magnum::Vector2i& size);
        void render(const SceneModel& scene,
                    const SelectionState& selection,
                    const Magnum::Matrix4& viewMatrix,
                    const Magnum::Matrix4& projectionMatrix,
                    const EditorPreferences& preferences);

        Magnum::GL::Texture2D& colorTexture() { return _colorTexture; }
        const Magnum::Vector2i& size() const { return _size; }
        const Magnum::Matrix4& viewMatrix() const { return _viewMatrix; }
        const Magnum::Matrix4& projectionMatrix() const { return _projectionMatrix; }

    private:
        void drawEntity(const SceneEntity& entity,
                        const Magnum::Matrix4& transform,
                        bool selected);
        void drawBounds(const SceneEntity& entity,
                        const Magnum::Matrix4& transform);

        Magnum::Vector2i _size{1, 1};
        Magnum::GL::Framebuffer _framebuffer{{{}, {1, 1}}};
        Magnum::GL::Texture2D _colorTexture;
        Magnum::GL::Renderbuffer _depth;
        Magnum::GL::Mesh _gridMesh;
        Magnum::GL::Mesh _axisMesh;
        Magnum::GL::Mesh _cubeMesh;
        Magnum::GL::Mesh _cylinderMesh;
        Magnum::GL::Mesh _sphereMesh;
        Magnum::GL::Mesh _wireCubeMesh;
        Magnum::Shaders::FlatGL3D _flatShader;
        Magnum::Shaders::PhongGL _phongShader;
        Magnum::Shaders::VertexColorGL3D _lineShader;
        Magnum::Matrix4 _viewMatrix{};
        Magnum::Matrix4 _projectionMatrix{};
};

}
