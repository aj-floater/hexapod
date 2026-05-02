#ifndef mesh_drawable_h
#define mesh_drawable_h

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

#include <Magnum/GL/Mesh.h>
#include <Magnum/Trade/AbstractImporter.h>
#include <Magnum/Trade/MeshData.h>
#include <Corrade/Containers/Optional.h>
#include <string>

typedef SceneGraph::Object<SceneGraph::TranslationRotationScalingTransformation3D> Object3D;
typedef SceneGraph::Scene<SceneGraph::TranslationRotationScalingTransformation3D> Scene3D;

static GL::Mesh loadMesh(const std::string& filePath) {
    // Create an instance of the importer
    PluginManager::Manager<Trade::AbstractImporter> manager;
    Magnum::Containers::Pointer<Magnum::Trade::AbstractImporter> importer = 
      manager.loadAndInstantiate("StlImporter");

    // Load the 3mf file
    if (!importer->openFile(filePath)) {
        // Handle the error if the file fails to load
        // (e.g., the file doesn't exist or is in an unsupported format)
        // You might want to throw an exception, log the error, or take any other action here
        // For simplicity, we'll just return an empty GL::Mesh
        return GL::Mesh();
    }

    // Get the mesh data (assuming it is the first and only mesh in the file)
    Magnum::Containers::Optional<Magnum::Trade::MeshData> meshData = importer->mesh(0);
    if (!meshData) {
        // Handle the error if the mesh data cannot be retrieved
        // You might want to throw an exception, log the error, or take any other action here
        // For simplicity, we'll just return an empty GL::Mesh
        return GL::Mesh();
    }

    // Compile the mesh data into a GL::Mesh
    Magnum::GL::Mesh mesh;
    mesh = Magnum::MeshTools::compile(*meshData);

    // Return the loaded GL::Mesh
    return mesh;
}

class MeshDrawable: public SceneGraph::Drawable3D {
  public:
    explicit MeshDrawable(Object3D& object, SceneGraph::DrawableGroup3D* group, Color3* color, std::string filePath):
      SceneGraph::Drawable3D{object, group}
    {
      _mesh = loadMesh(filePath);

      // Debug{} << "Loaded mesh file";

      // _mesh = MeshTools::compile(Primitives::cubeSolid());
      _color = color;
    }
    bool visible = true;

  private:
    void draw(const Matrix4& transformationMatrix, SceneGraph::Camera3D& camera) override {
      if (visible){
        using namespace Math::Literals;

        (_shader)
          .setLightPosition(Vector3{-1.0f, -1.0f, -1.0f})
          // .setLightColor(Color3{1.0f, 1.0f, 1.0f})
          .setDiffuseColor(*_color)
          .setAmbientColor(*_color * 0.5f)
          .setTransformationMatrix(transformationMatrix)
          .setNormalMatrix(transformationMatrix.normalMatrix())
          .setProjectionMatrix(camera.projectionMatrix())
          .draw(_mesh);
      }
    }

    GL::Mesh _mesh;
    Shaders::PhongGL _shader;
    Color3* _color;
};

#endif