#include <Corrade/TestSuite/Tester.h>
#include <Corrade/TestSuite/Compare/Numeric.h>

#include "editor/MathUtils.h"
#include "editor/SceneModel.h"

namespace hexapod::simulation::test {

class SceneModelTest: public Corrade::TestSuite::Tester {
    public:
        explicit SceneModelTest() {
            addTests({
                &SceneModelTest::defaultSceneHasEntities,
                &SceneModelTest::childTransformIsHierarchical,
                &SceneModelTest::raycastReturnsNearestVisibleEntity,
                &SceneModelTest::visibleBoundsIgnoreHiddenEntities
            });
        }

    private:
        void defaultSceneHasEntities();
        void childTransformIsHierarchical();
        void raycastReturnsNearestVisibleEntity();
        void visibleBoundsIgnoreHiddenEntities();
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

}

CORRADE_TEST_MAIN(hexapod::simulation::test::SceneModelTest)
