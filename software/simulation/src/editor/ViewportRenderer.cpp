#include "ViewportRenderer.h"

#include <Magnum/Math/Functions.h>
#include <Magnum/GL/DefaultFramebuffer.h>
#include <Magnum/GL/RenderbufferFormat.h>
#include <Magnum/GL/Renderer.h>
#include <Magnum/GL/TextureFormat.h>
#include <Magnum/MeshTools/Compile.h>
#include <Magnum/Primitives/Axis.h>
#include <Magnum/Primitives/Cube.h>
#include <Magnum/Primitives/Cylinder.h>
#include <Magnum/Primitives/Grid.h>
#include <Magnum/Trade/MeshData.h>
#include <Magnum/Primitives/UVSphere.h>

using namespace Magnum::Math::Literals;

namespace hexapod::simulation {

namespace {

Magnum::Color3 brighten(const Magnum::Color3& color, const Magnum::Float factor) {
    return Magnum::Color3{
        Magnum::Math::min(color.r()*factor, 1.0f),
        Magnum::Math::min(color.g()*factor, 1.0f),
        Magnum::Math::min(color.b()*factor, 1.0f)};
}

}

ViewportRenderer::ViewportRenderer():
    _gridMesh{Magnum::MeshTools::compile(Magnum::Primitives::grid3DWireframe({40, 40}))},
    _axisMesh{Magnum::MeshTools::compile(Magnum::Primitives::axis3D())},
    _cubeMesh{Magnum::MeshTools::compile(Magnum::Primitives::cubeSolid())},
    _cylinderMesh{Magnum::MeshTools::compile(Magnum::Primitives::cylinderSolid(1, 24, 1.0f, Magnum::Primitives::CylinderFlag::CapEnds))},
    _sphereMesh{Magnum::MeshTools::compile(Magnum::Primitives::uvSphereSolid(12, 24))},
    _wireCubeMesh{Magnum::MeshTools::compile(Magnum::Primitives::cubeWireframe())},
    _phongShader{}
{
    _phongShader.setLightPositions({{7.0f, 11.0f, 8.0f, 0.0f}});
    ensureSize(_size);
}

void ViewportRenderer::ensureSize(const Magnum::Vector2i& size) {
    const Magnum::Vector2i clamped{Magnum::Math::max(size.x(), 1), Magnum::Math::max(size.y(), 1)};
    if(clamped == _size) return;

    _size = clamped;
    _framebuffer = Magnum::GL::Framebuffer{{{}, _size}};
    _colorTexture = Magnum::GL::Texture2D{};
    _depth = Magnum::GL::Renderbuffer{};

    _colorTexture
        .setMagnificationFilter(Magnum::GL::SamplerFilter::Linear)
        .setMinificationFilter(Magnum::GL::SamplerFilter::Linear)
        .setWrapping(Magnum::GL::SamplerWrapping::ClampToEdge)
        .setStorage(1, Magnum::GL::TextureFormat::RGBA8, _size);
    _depth.setStorage(Magnum::GL::RenderbufferFormat::DepthComponent24, _size);

    _framebuffer
        .attachTexture(Magnum::GL::Framebuffer::ColorAttachment{0}, _colorTexture, 0)
        .attachRenderbuffer(Magnum::GL::Framebuffer::BufferAttachment::Depth, _depth)
        .mapForDraw({{Magnum::Shaders::FlatGL3D::ColorOutput, Magnum::GL::Framebuffer::ColorAttachment{0}}});
}

void ViewportRenderer::render(const SceneModel& scene,
                              const SelectionState& selection,
                              const Magnum::Matrix4& viewMatrix,
                              const Magnum::Matrix4& projectionMatrix,
                              const EditorPreferences& preferences) {
    _viewMatrix = viewMatrix;
    _projectionMatrix = projectionMatrix;

    _framebuffer.bind();
    _framebuffer.clear(Magnum::GL::FramebufferClear::Color|Magnum::GL::FramebufferClear::Depth);

    Magnum::GL::Renderer::enable(Magnum::GL::Renderer::Feature::DepthTest);
    Magnum::GL::Renderer::enable(Magnum::GL::Renderer::Feature::FaceCulling);
    _phongShader.setLightPositions({_viewMatrix*Magnum::Vector4{7.0f, 11.0f, 8.0f, 0.0f}});

    if(preferences.showGrid) {
        const Magnum::Matrix4 gridTransform =
            Magnum::Matrix4::rotationX(Magnum::Deg{90.0f})*
            Magnum::Matrix4::scaling({10.0f, 10.0f, 10.0f});
        _flatShader
            .setColor(0x3a4556_rgbf)
            .setTransformationProjectionMatrix(_projectionMatrix*_viewMatrix*gridTransform)
            .draw(_gridMesh);
    }

    if(preferences.showAxes) {
        _lineShader
            .setTransformationProjectionMatrix(_projectionMatrix*_viewMatrix)
            .draw(_axisMesh);
    }

    for(const SceneEntity& entity: scene.entities()) {
        if(!entity.visible) continue;

        const Magnum::Matrix4 transform = scene.worldTransform(Magnum::Int(entity.id));
        const bool selected = selection.selectedId == Magnum::Int(entity.id);
        drawEntity(entity, transform, selected);

        if(selected && preferences.showBounds)
            drawBounds(entity, transform);
    }

    Magnum::GL::defaultFramebuffer.bind();
}

void ViewportRenderer::drawEntity(const SceneEntity& entity,
                                  const Magnum::Matrix4& transform,
                                  const bool selected) {
    const Magnum::Color3 diffuse = brighten(entity.color.rgb(), selected ? 1.2f : 1.0f);
    const Magnum::Matrix4 cameraTransform = _viewMatrix*transform;
    _phongShader
        .setAmbientColor(diffuse*0.24f)
        .setDiffuseColor(diffuse)
        .setSpecularColor(0x111111_rgbf)
        .setShininess(40.0f)
        .setProjectionMatrix(_projectionMatrix)
        .setTransformationMatrix(cameraTransform)
        .setNormalMatrix(cameraTransform.normalMatrix());

    switch(entity.primitive) {
        case PrimitiveKind::Cylinder:
            _phongShader.draw(_cylinderMesh);
            break;
        case PrimitiveKind::Sphere:
            _phongShader.draw(_sphereMesh);
            break;
        case PrimitiveKind::Cube:
        default:
            _phongShader.draw(_cubeMesh);
            break;
    }
}

void ViewportRenderer::drawBounds(const SceneEntity& entity,
                                  const Magnum::Matrix4& transform) {
    const Magnum::Range3D bounds = entity.localBounds();
    const Magnum::Vector3 boundsScale = bounds.size();
    const Magnum::Matrix4 boundsTransform =
        transform*
        Magnum::Matrix4::translation(bounds.center())*
        Magnum::Matrix4::scaling(boundsScale);

    _flatShader
        .setColor(0xdadfe6_rgbf)
        .setTransformationProjectionMatrix(_projectionMatrix*_viewMatrix*boundsTransform)
        .draw(_wireCubeMesh);
}

}
