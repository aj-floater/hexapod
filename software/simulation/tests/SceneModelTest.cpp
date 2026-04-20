#include <Corrade/TestSuite/Tester.h>
#include <Corrade/TestSuite/Compare/Numeric.h>

#include "editor/ArcBall.h"
#include "editor/MathUtils.h"
#include "editor/SceneModel.h"

namespace hexapod::simulation::test {

class SceneModelTest: public Corrade::TestSuite::Tester {
    public:
        explicit SceneModelTest() {
            addTests({
                &SceneModelTest::defaultSceneHasEntities,
                &SceneModelTest::childTransformIsHierarchical,
                &SceneModelTest::childTransformsIgnoreParentScale,
                &SceneModelTest::raycastReturnsNearestVisibleEntity,
                &SceneModelTest::visibleBoundsIgnoreHiddenEntities,
                &SceneModelTest::turntableCameraHasNoRoll,
                &SceneModelTest::turntableCameraPreservesEyePosition
            });
        }

    private:
        void defaultSceneHasEntities();
        void childTransformIsHierarchical();
        void childTransformsIgnoreParentScale();
        void raycastReturnsNearestVisibleEntity();
        void visibleBoundsIgnoreHiddenEntities();
        void turntableCameraHasNoRoll();
        void turntableCameraPreservesEyePosition();
};

void SceneModelTest::defaultSceneHasEntities() {
    SceneModel scene;
    CORRADE_COMPARE(scene.entities().size(), 5);
    CORRADE_VERIFY(scene.findEntity(3));
}

void SceneModelTest::childTransformIsHierarchical() {
    SceneModel scene;
    const Magnum::Matrix4 joint = scene.worldTransform(2);
    const Magnum::Matrix4 link = scene.worldTransform(3);
    const hexapod::simulation::SceneEntity* entity = scene.findEntity(3);

    CORRADE_VERIFY(entity);
    CORRADE_VERIFY(link.translation() != entity->localTransform.translation);
    CORRADE_VERIFY(link.translation().y() > joint.translation().y());
}

void SceneModelTest::childTransformsIgnoreParentScale() {
    SceneModel scene;
    const Magnum::Matrix4 endEffector = scene.worldTransform(4);
    const Magnum::Matrix3x3 rotationScaling = endEffector.rotationScaling();

    CORRADE_COMPARE_WITH(rotationScaling[0].length(), 0.26f, Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
    CORRADE_COMPARE_WITH(rotationScaling[1].length(), 0.26f, Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
    CORRADE_COMPARE_WITH(rotationScaling[2].length(), 0.26f, Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
}

void SceneModelTest::raycastReturnsNearestVisibleEntity() {
    SceneModel scene;
    const std::optional<SceneRayHit> hit = scene.raycast(Ray3D{
        {-10.0f, 0.35f, -1.5f},
        Magnum::Vector3::xAxis()});

    CORRADE_VERIFY(hit);
    CORRADE_COMPARE(hit->entityId, 5);
    CORRADE_COMPARE_WITH(hit->worldPosition.y(), 0.35f, Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
}

void SceneModelTest::visibleBoundsIgnoreHiddenEntities() {
    SceneModel scene;
    SceneEntity* reference = scene.findEntity(5);
    CORRADE_VERIFY(reference);

    const std::optional<Magnum::Range3D> originalBounds = scene.visibleBounds();
    reference->visible = false;
    const std::optional<Magnum::Range3D> hiddenBounds = scene.visibleBounds();

    CORRADE_VERIFY(originalBounds);
    CORRADE_VERIFY(hiddenBounds);
    CORRADE_VERIFY(originalBounds->min().x() < hiddenBounds->min().x());
}

void SceneModelTest::turntableCameraHasNoRoll() {
    Magnum::Examples::ArcBall camera{
        {5.4f, 4.2f, 6.2f},
        {0.0f, 0.0f, 0.0f},
        Magnum::Vector3::yAxis(),
        ViewportVerticalFov,
        {1280, 720}};

    camera.initTransformation({320.0f, 240.0f});
    camera.rotate({910.0f, 120.0f});
    camera.updateTransformation();

    const Magnum::Vector3 right = camera.transformationMatrix()
        .transformVector(Magnum::Vector3::xAxis())
        .normalized();
    CORRADE_COMPARE_WITH(
        Magnum::Math::abs(Magnum::Math::dot(right, camera.worldUp())),
        0.0f,
        Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
}

void SceneModelTest::turntableCameraPreservesEyePosition() {
    const Magnum::Vector3 eye{5.4f, 4.2f, 6.2f};
    Magnum::Examples::ArcBall camera{
        eye,
        {0.0f, 0.0f, 0.0f},
        -Magnum::Vector3::yAxis(),
        ViewportVerticalFov,
        {1280, 720}};

    const Magnum::Vector3 actualEye = camera.transformationMatrix().translation();
    CORRADE_COMPARE_WITH(actualEye.x(), eye.x(), Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
    CORRADE_COMPARE_WITH(actualEye.y(), eye.y(), Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
    CORRADE_COMPARE_WITH(actualEye.z(), eye.z(), Corrade::TestSuite::Compare::around(Magnum::Float{1.0e-4f}));
}

}

CORRADE_TEST_MAIN(hexapod::simulation::test::SceneModelTest)
