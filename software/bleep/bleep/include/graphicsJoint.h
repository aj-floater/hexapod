#ifndef graphics_joint_h
#define graphics_joint_h

#include "joint.h"

#include <Magnum/Math/Color.h>

// Forward declarations
extern SceneGraph::DrawableGroup3D _drawables;
extern Scene3D _scene;

class GraphicsJoint;

class GraphicsJoint : public Joint {
public:
  // Constructors
  GraphicsJoint() : _child(nullptr) {
      // null constructor
  }

  GraphicsJoint(Color3 color, Float scale, Vector3 axisofrotation, Float length)
    : Joint(axisofrotation, length), _scale(Vector3(scale)), _child(nullptr)
  {
    _color = color;
    initCubeDrawObject();
  }

  void graphicsUpdate(Vector3 position, Quaternion rotation) {
    // Update position and rotation code
    _rotation = rotation * Quaternion::rotation(Rad(_angle), _axisofrotation);
    _position = position;

    // Recursively update child joints
    if (_child) {
        position += _rotation.transformVector(_length * Vector3::xAxis());
        _child->graphicsUpdate(position, _rotation);
    }

    updateDrawObject();
  }

  // Function to add a child joint to this joint
  GraphicsJoint* addChild(Color3 color, Float scale, Vector3 axisofrotation, Float length){
    _child = new GraphicsJoint(color, scale, axisofrotation, length);
    return _child;
  }

  // Function to initialize the CubeDrawable for visualization
  void initCubeDrawObject() {
      _cubeobject = new Object3D{&_scene};
      (*_cubeobject)
          .setRotation(_rotation)
          .setTranslation(_position)
          .scale(Vector3(0.1f));

      // Create the CubeDrawable with the specified meshFile
      _cubedrawable = new CubeDrawable{*_cubeobject, &_drawables, Color3::red()};
  }

  // Function to initialize the MeshDrawable for visualization
  void initMeshDrawObject(std::string meshFile) {
      _meshobject = new Object3D{&_scene};
      (*_meshobject)
          .setRotation(_rotation)
          .setTranslation(_position)
          .scale(_scale);

      // Create the MeshDrawable with the specified meshFile
      _meshdrawable = new MeshDrawable{*_meshobject, &_drawables, &_color, meshFile};
  }

  // Function to update the visual representation of the joint
  void updateDrawObject() {
      (*_meshobject)
          .setRotation(_rotation * _meshrotation)
          .setTranslation(_position + _rotation.transformVector(_meshposition))
          .setScaling(_scale);
      (*_cubeobject)
          .setRotation(_rotation)
          .setTranslation(_position);
  }

  // Function to get joint information as a string
  std::string getJointInfo() const {
      std::stringstream info;

      info << "Length: " << _length << "\n";
      info << "Scale: " << _scale.x() << "\n";
      info << "Axis of Rotation: (" << _axisofrotation.x() << ", " << _axisofrotation.y() << ", " << _axisofrotation.z() << ")\n";
      info << "Current Angle: " << _angle << "\n";
      info << "Position: (" << _position.x() << ", " << _position.y() << ", " << _position.z() << ")\n";
      info << "Rotation: (" << _rotation.vector().x() << ", " << _rotation.vector().y() << ", " << _rotation.vector().z() << ", " << _rotation.scalar() << ")\n";

      return info.str();
  }

  Object3D* _cubeobject;
  Object3D* _meshobject;
  CubeDrawable* _cubedrawable; // pointer to the created cubedrawable
  MeshDrawable* _meshdrawable;
  Vector3 _meshposition;
  Quaternion _meshrotation;
  Vector3 _scale;
  Color3 _color;

  GraphicsJoint* _child;
};

#endif