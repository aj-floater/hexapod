#ifndef graphics_leg_h
#define graphics_leg_h

#include "leg.h"
#include "graphicsJoint.h"

#include <Magnum/Math/Color.h>

#include "cube.h"

class GraphicsLeg : public Leg {
public:
    GraphicsLeg(Vector3 inputColor){
        // Initialize features of base joint
        // Initialize features of second joint
        // Initialize features of third joint

        _color = inputColor;

        EndEffector = new GraphicsJoint(Color3(0.9f, 0.0f, 0.0f), 10.1f, Vector3::yAxis(), 1.0f);

        BaseJoint = new GraphicsJoint(_color, 10.1f, Vector3::yAxis(), 0.48f);
        BaseJoint->_meshposition = Vector3(0.48f, 0.0f, 0.0f);
        BaseJoint->_meshrotation = Quaternion::rotation(270.0_degf, Vector3::xAxis());
        BaseJoint->initMeshDrawObject(std::string(MODELS_DIR) + "/baseJoint.stl");

        SecondJoint = BaseJoint->addChild(_color * _color, 10.1f, Vector3::zAxis(), 0.6f);
        SecondJoint->_meshposition = Vector3(0.6f, 0.0f, 0.0f);
        SecondJoint->_meshrotation = Quaternion::rotation(270.0_degf, Vector3::xAxis());
        SecondJoint->initMeshDrawObject(std::string(MODELS_DIR) + "/secondJoint.stl");

        ThirdJoint = SecondJoint->addChild(_color * _color * _color, 10.1f, Vector3::zAxis(), 1.3f);
        ThirdJoint->_meshposition = Vector3(1.325f, 0.0f, 0.0f);
        ThirdJoint->_meshrotation = Quaternion::rotation(270.0_degf, Vector3::xAxis());
        ThirdJoint->initMeshDrawObject(std::string(MODELS_DIR) + "/thirdJoint.stl");

        desiredPoseCube = new Cube(Color3(0.2f, 0.2f, 0.9f), 0.1f, _finalAnimationPose);
    } 

    void CalculateIK(){
        Vector3 startPosition = _position;
        Vector3 endPosition = _endPose;

        Quaternion _invertedRotation = _rotation.inverted();
        endPosition = _invertedRotation.transformVector(endPosition);
        startPosition = _invertedRotation.transformVector(startPosition);
        
        Vector3 deltaPosition = endPosition - startPosition;


        Float angle_1 = atan2f(deltaPosition.z(), deltaPosition.x());

        Float x = (endPosition.z()/sinf(angle_1)) - ((startPosition.z()/sinf(angle_1)) + BaseJoint->_length);
        if (startPosition.z() == endPosition.z())
            x = (endPosition.x()/cosf(angle_1)) - ((startPosition.x()/cosf(angle_1)) + BaseJoint->_length);

        Float y = - deltaPosition.y();

        Float l1 = SecondJoint->_length;
        Float l2 = ThirdJoint->_length;

        // Calculate angle 2
        Float angle_3 = acosf((- powf(l1, 2) - powf(l2, 2) + powf(x, 2) + powf(y, 2))/(2*l1*l2));
        
        // Calculate angle 1
        Float angle_2 = atan2f(y,x) - atan2f((l2*sinf(angle_3)),(l1+l2*cosf(angle_3)));

        if (!std::isnan(angle_1) && !std::isnan(angle_2) && !std::isnan(angle_3)){
            SecondJoint->_angle = - angle_2;
            ThirdJoint->_angle = - angle_3;
        }
        BaseJoint->_angle = - angle_1;
    }

    void update(float deltaTime){
        HandleAnimation(deltaTime);

        // Calculate the inverse kinematics
        if (showIK)
            CalculateIK();

        desiredPoseCube->update(_finalAnimationPose);

        // Propagate throughout all joints in the leg
        // to calculate the forward kinematics given the individual joint angles
        BaseJoint->graphicsUpdate(_position, _rotation);
        
        // (*EndEffector->_cubeobject)
        //     .setTranslation(_endPose);

        BaseJoint->_color = _color;
        SecondJoint->_color = _color * _color;
        ThirdJoint->_color = _color * _color * _color;

        // Update cube visibility based on showCubes flag
        EndEffector->_cubedrawable->visible = showCubes;
        BaseJoint->_cubedrawable->visible = showCubes;
        SecondJoint->_cubedrawable->visible = showCubes;
        ThirdJoint->_cubedrawable->visible = showCubes;

        // Update mesh visibility based on showMeshes flag
        BaseJoint->_meshdrawable->visible = showMeshes;
        SecondJoint->_meshdrawable->visible = showMeshes;
        ThirdJoint->_meshdrawable->visible = showMeshes;
    }

    // Function to get leg information as a string
    std::string getLegInfo() const {
        std::stringstream info;

        info << "Leg Position: (" << _position.x() << ", " << _position.y() << ", " << _position.z() << ")\n";
        // info << "Leg Rotation: (" << _rotation.x() << ", " << _rotation.y() << ", " << _rotation.z() << ", " << _rotation.scalar() << ")\n";
        info << "----- Base Joint Info -----\n";
        info << BaseJoint->getJointInfo();
        info << "----- Second Joint Info -----\n";
        info << SecondJoint->getJointInfo();
        info << "----- Third Joint Info -----\n";
        info << ThirdJoint->getJointInfo();

        return info.str();
    }

    void showDebugging(){
        { // Old Debugging
            ImGui::Begin("Old Debugging");
            if (ImGui::RadioButton("Show Leg Info", showLegInfoWindow)){
                showLegInfoWindow = !showLegInfoWindow; // Set the flag to true when the button is clicked
            }
            if (ImGui::RadioButton("Show Meshes", showMeshes)){
                showMeshes = !showMeshes; // Set the flag to true when the button is clicked
            }
            if (ImGui::RadioButton("Show Cubes", showCubes)){
                showCubes = !showCubes; // Set the flag to true when the button is clicked
            }
            if (ImGui::RadioButton("Calculate IK", showIK)){
                showIK = !showIK; // Set the flag to true when the button is clicked
            }

            ImGui::ColorEdit3("Leg Color", _color.data());

            ImGui::SeparatorText("Leg Position and Rotation");
            ImGui::PushItemWidth(120);
            float legposition[3] = {
            _position.x(),
            _position.y(),
            _position.z()
            };
            if (ImGui::DragFloat3("Position - Leg", legposition, 0.01f)){
            _position = Vector3(
                legposition[0],
                legposition[1],
                legposition[2]
            );
            }
            ImGui::PushItemWidth(120);
            float legendpose[3] = {
            _endPose.x(),
            _endPose.y(),
            _endPose.z()
            };
            if (ImGui::DragFloat3("End Pose - Leg", legendpose, 0.01f)){
            _endPose = Vector3(
                legendpose[0],
                legendpose[1],
                legendpose[2]
            );
            }
            // float legdesiredpose[3] = {
            // _desiredPose.x(),
            // _desiredPose.y(),
            // _desiredPose.z()
            // };
            // if (ImGui::DragFloat3("Desired Pose - Leg", legdesiredpose, 0.01f)){
            // _desiredPose = Vector3(
            //     legdesiredpose[0],
            //     legdesiredpose[1],
            //     legdesiredpose[2]
            // );
            // }

            
            ImGui::PushItemWidth(120);
            if(
            ImGui::DragFloat3("Rotation - Leg", legrotation, 0.01f)
            ){
            Quaternion combinedRotation;
            combinedRotation = combinedRotation * Quaternion::rotation(Rad(legrotation[0]), Vector3::xAxis()); 
            combinedRotation = combinedRotation * Quaternion::rotation(Rad(legrotation[1]), Vector3::yAxis()); 
            combinedRotation = combinedRotation * Quaternion::rotation(Rad(legrotation[2]), Vector3::zAxis());

            _rotation = combinedRotation;
            }


            ImGui::SeparatorText("Joint Angles");
            ImGui::PushItemWidth(60);
            ImGui::DragFloat("Angle - Base Joint", &BaseJoint->_angle, 0.1f);
            ImGui::DragFloat("Angle - Second Joint", &SecondJoint->_angle, 0.1f);
            ImGui::DragFloat("Angle - Third Joint", &ThirdJoint->_angle, 0.1f);

            if (ImGui::BeginMenu("Further Debugging")){
            ImGui::SeparatorText("Joint Lengths");
            ImGui::PushItemWidth(60);
            ImGui::DragFloat("Length - Base Joint", &BaseJoint->_length, 0.1f);
            ImGui::DragFloat("Length - Second Joint", &SecondJoint->_length, 0.1f);
            ImGui::DragFloat("Length - Third Joint", &ThirdJoint->_length, 0.1f);

            ImGui::SeparatorText("Joint Scales");
            ImGui::PushItemWidth(60);
            float bscale = BaseJoint->_scale.x();
            if (ImGui::DragFloat("Scale - Base Joint", &bscale, 0.1f)){
                BaseJoint->_scale = Vector3(bscale);
            }
            float sscale = SecondJoint->_scale.x();
            if (ImGui::DragFloat("Scale - Second Joint", &sscale, 0.1f)){
                SecondJoint->_scale = Vector3(sscale);
            }
            float tscale = ThirdJoint->_scale.x();
            if (ImGui::DragFloat("Scale - Third Joint", &tscale, 0.1f)){
                ThirdJoint->_scale = Vector3(tscale);
            }
            ImGui::SeparatorText("Joint Mesh Rotations");
            ImGui::PushItemWidth(120);
            float basemeshrotationvector[3] = {0.0f, 0.0f, 0.0f};
            if(
                ImGui::DragFloat3("Rotation - Base Joint", basemeshrotationvector, 0.1f)
            ){
                BaseJoint->_meshrotation = BaseJoint->_meshrotation * Quaternion::rotation(Rad(basemeshrotationvector[0]), Vector3::xAxis()); 
                BaseJoint->_meshrotation = BaseJoint->_meshrotation * Quaternion::rotation(Rad(basemeshrotationvector[1]), Vector3::yAxis()); 
                BaseJoint->_meshrotation = BaseJoint->_meshrotation * Quaternion::rotation(Rad(basemeshrotationvector[2]), Vector3::zAxis()); 
            }
            ImGui::PushItemWidth(120);
            float secondmeshrotationvector[3] = {0.0f, 0.0f, 0.0f};
            if(
                ImGui::DragFloat3("Rotation - Second Joint", secondmeshrotationvector, 0.1f)
            ){
                SecondJoint->_meshrotation = SecondJoint->_meshrotation * Quaternion::rotation(Rad(secondmeshrotationvector[0]), Vector3::xAxis()); 
                SecondJoint->_meshrotation = SecondJoint->_meshrotation * Quaternion::rotation(Rad(secondmeshrotationvector[1]), Vector3::yAxis()); 
                SecondJoint->_meshrotation = SecondJoint->_meshrotation * Quaternion::rotation(Rad(secondmeshrotationvector[2]), Vector3::zAxis()); 
            }
            float thirdmeshrotationvector[3] = {0.0f, 0.0f, 0.0f};
            if(
                ImGui::DragFloat3("Rotation - Third Joint", thirdmeshrotationvector, 0.1f)
            ){
                ThirdJoint->_meshrotation = ThirdJoint->_meshrotation * Quaternion::rotation(Rad(thirdmeshrotationvector[0]), Vector3::xAxis()); 
                ThirdJoint->_meshrotation = ThirdJoint->_meshrotation * Quaternion::rotation(Rad(thirdmeshrotationvector[1]), Vector3::yAxis()); 
                ThirdJoint->_meshrotation = ThirdJoint->_meshrotation * Quaternion::rotation(Rad(thirdmeshrotationvector[2]), Vector3::zAxis()); 
            }
            ImGui::SeparatorText("Joint Mesh Positions");
            float basemeshposition[3] = {
                BaseJoint->_meshposition.x(),
                BaseJoint->_meshposition.y(),
                BaseJoint->_meshposition.z()
            };
            if (ImGui::DragFloat3("Position - Base Joint", basemeshposition, 0.1f)){
                BaseJoint->_meshposition = Vector3(
                basemeshposition[0],
                basemeshposition[1],
                basemeshposition[2]
                );
            }
            float secondmeshposition[3] = {
                SecondJoint->_meshposition.x(),
                SecondJoint->_meshposition.y(),
                SecondJoint->_meshposition.z()
            };
            if (ImGui::DragFloat3("Position - Second Joint", secondmeshposition, 0.1f)){
                SecondJoint->_meshposition = Vector3(
                secondmeshposition[0],
                secondmeshposition[1],
                secondmeshposition[2]
                );
            }
            float thirdmeshposition[3] = {
                ThirdJoint->_meshposition.x(),
                ThirdJoint->_meshposition.y(),
                ThirdJoint->_meshposition.z()
            };
            if (ImGui::DragFloat3("Position - Third Joint", thirdmeshposition, 0.1f)){
                ThirdJoint->_meshposition = Vector3(
                thirdmeshposition[0],
                thirdmeshposition[1],
                thirdmeshposition[2]
                );
            }

            ImGui::EndMenu();
            }
            if (showLegInfoWindow) {
            // Open a new ImGui window to display the leg information
            // Get the leg information using getLegInfo() (assuming debuggingLeg is a valid pointer)
            // Display the leg information in the window
            // ImGui::Begin("Leg Information", &showLegInfoWindow, ImGuiWindowFlags_AlwaysAutoResize);
            std::string legInfo = getLegInfo();
            ImGui::Text("%s", legInfo.c_str());

            // ImGui::End();
            }

            ImGui::End();
        }
    } 

    GraphicsJoint* BaseJoint;
    GraphicsJoint* SecondJoint;
    GraphicsJoint* ThirdJoint;

    GraphicsJoint* EndEffector;

    Color3 _color;

    Cube* desiredPoseCube;

    bool showCubes = false;
    bool showMeshes = true;
    bool showLegInfoWindow = true; // A flag to track whether to show the leg info window or not
    bool showDebuggingWindow = false;
    float legrotation[3] = {0.0f, 0.0f, 0.0f};
};
#endif