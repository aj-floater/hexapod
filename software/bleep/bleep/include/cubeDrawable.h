#ifndef cube_drawable_h
#define cube_drawable_h

#include <Magnum/Platform/Sdl2Application.h>
#include <Magnum/SceneGraph/Scene.h>
#include <Magnum/SceneGraph/TranslationRotationScalingTransformation3D.h>
#include <Magnum/SceneGraph/AbstractTranslationRotationScaling3D.h>
#include <Magnum/SceneGraph/Camera.h>
#include <Magnum/SceneGraph/Drawable.h>

#include <Magnum/Primitives/Cube.h>
#include <Magnum/Primitives/Grid.h>
#include <Magnum/MeshTools/Compile.h>
#include <Magnum/Shaders/PhongGL.h>
#include <Magnum/Math/Color.h>
#include <Magnum/GL/Mesh.h>
#include <Magnum/Trade/MeshData.h>

typedef SceneGraph::Object<SceneGraph::TranslationRotationScalingTransformation3D> Object3D;
typedef SceneGraph::Scene<SceneGraph::TranslationRotationScalingTransformation3D> Scene3D;

class CubeDrawable: public SceneGraph::Drawable3D {
  public:
    explicit CubeDrawable(Object3D& object, SceneGraph::DrawableGroup3D* group, Color3 color):
      SceneGraph::Drawable3D{object, group}
    {
      _mesh = MeshTools::compile(Primitives::cubeSolid());
      _color = color;
    }
    bool visible = true;

  private:
    void draw(const Matrix4& transformationMatrix, SceneGraph::Camera3D& camera) override {
      if (visible){
        using namespace Math::Literals;

        (_shader)
          .setDiffuseColor(_color)
          .setAmbientColor(_color * 0.2)
          .setTransformationMatrix(transformationMatrix)
          .setNormalMatrix(transformationMatrix.normalMatrix())
          .setProjectionMatrix(camera.projectionMatrix())
          .draw(_mesh);
      }
    }

    GL::Mesh _mesh;
    Shaders::PhongGL _shader;
    Color3 _color;
};

#endif