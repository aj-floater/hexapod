#ifndef cube_h
#define cube_h

#include <Magnum/Math/Color.h>

class Cube {
public:
  Cube(): 
    _shown(false), _color(Color3(0.0f)), _scale(0.0f), _position(Vector3(0.0f)), _rotation(Quaternion()) {
      // null constructor
  }

  Cube(Color3 color, Float scale, Vector3 position):
    _color(color), _scale(scale), _position(position), _shown(true) {
      
      initDrawObject();
  }

  void update(Vector3 position) {
    _position = position;

    updateDrawObject();
  }

  // Function to initialize the CubeDrawable for visualization
  void initDrawObject() {
      _cubeobject = new Object3D{&_scene};
      (*_cubeobject)
          .setRotation(_rotation)
          .setTranslation(_position)
          .scale(_scale);

      // Create the CubeDrawable with the specified meshFile
      _cubedrawable = new CubeDrawable{*_cubeobject, &_drawables, _color};
  }

  // Function to update the visual representation of the joint
  void updateDrawObject() {
      (*_cubeobject)
          .setRotation(_rotation)
          .setTranslation(_position);
  }

  Object3D* _cubeobject;
  CubeDrawable* _cubedrawable; // pointer to the created cubedrawable
  Vector3 _scale;
  Vector3 _position;
  Quaternion _rotation;

  Color3 _color;
  bool _shown;
};

#endif