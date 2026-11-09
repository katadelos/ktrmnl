import QtQuick 2.15
import QtQuick.Window 2.15

// The simulator presents the same logical viewport and dark palette as the app.
Window {
    id: root
    objectName: "ktrmnlSimulatorWindow"
    // Headless uses Qt's offscreen platform, so keeping the window exposed is
    // safe and lets synthetic pointer events exercise the same MouseAreas.
    visible: true
    width: simulatorDisplay.logicalWidth
    height: simulatorDisplay.logicalHeight
    color: simulatorDisplay.nightMode ? "#000000" : "#ffffff"
    title: "ktrmnl2 — " + width + " × " + height + " simulator"
    flags: Qt.Window

    property alias menuOpen: appView.menuOpen
    property alias menuPage: appView.menuPage
    property alias menuIndex: appView.menuIndex
    property bool keyboardVisible: appView.entryKeyboardVisible
    property alias simulatorPanelOpen: simulatorPanel.open
    property alias simulatorPanelTab: simulatorPanel.activeTab
    readonly property bool firstRunActive: appView.onboardingActive
    readonly property bool languageSelectionActive: appView.languageSelectionActive
    readonly property bool firstRunWelcomeActive: appView.welcomeActive
    readonly property string appOverlay: appView.appOverlay
    readonly property real simulatorTextScale: simulatorControls.textScale
    readonly property real simulatorRowHeightScale: simulatorControls.rowHeightScale
    readonly property int simulatorMenuRowHeight: appView.menuRowHeight
    readonly property real simulatorKeyboardHeightRatio: simulatorControls.keyboardHeightRatio
    readonly property int simulatorNativeWidth: simulatorDisplay.nativeWidth
    readonly property int simulatorNativeHeight: simulatorDisplay.nativeHeight
    readonly property string simulatorLanguage: i18n.language

    function openMenu(page) { appView.openMenu(page) }
    function closeMenu() { appView.closeMenu() }
    function handleAction(action) { appView.handleAction(action, false) }
    function showFirstRun() { appView.showFirstRunPreview() }

    function setSimulatorFirstRun(active) {
        simulatorControls.setFirstRunActive(Boolean(active))
        if (active)
            appView.showFirstRunPreview()
        else
            appView.finishFirstRunPreview()
    }

    AppView {
        id: appView
        anchors.fill: parent
        controller: ktrmnl
        contentModel: content
        wifiBackend: wifi
        inputBackend: inputBridge
        translator: i18n
        paperColor: simulatorDisplay.nightMode ? "#000000" : "#ffffff"
        inkColor: simulatorDisplay.nightMode ? "#ffffff" : "#000000"
        textScale: simulatorControls.textScale
        rowHeightScale: simulatorControls.rowHeightScale
        keyboardHeightRatio: simulatorControls.keyboardHeightRatio
        initialMenuOpen: runtimeInitialMenuOpen
        initialMenuPage: runtimeInitialMenuPage
    }

    SimulatorPanel {
        id: simulatorPanel
        anchors.fill: parent
        visible: runtimeSimulatorPanelEnabled
        drawer: runtimeInitialSimulatorPanelOpen ? SimulatorPanel.Open : SimulatorPanel.Closed
        z: 1000
        controls: simulatorControls
        displayBackend: simulatorDisplay
        controller: ktrmnl
        wifiBackend: wifi
        contentModel: content
        translator: i18n
        firstRunActive: appView.onboardingActive
        onFirstRunStateRequested: function(active) {
            root.setSimulatorFirstRun(active)
        }
        onPageRequested: function(page) {
            if (page === "first-run") {
                root.setSimulatorFirstRun(true)
                return
            }
            if (page === "status")
                ktrmnl.refreshDeviceStatus()
            appView.openMenu(page)
        }

        onDismissed: appView.forceActiveFocus()
    }

    Component.onCompleted: {
        if (runtimeInitialEditSetting.length > 0)
            Qt.callLater(function() { appView.openSetting(runtimeInitialEditSetting) })
    }

    enum Capture { Disabled, Waiting, Capturing, Finished }
    property int captureState: runtimeScreenshotPath.length > 0 ? SimulatorMain.Waiting : SimulatorMain.Disabled
    Timer {
        interval: content.busy ? 1000 : 350
        repeat: false
        running: root.captureState === SimulatorMain.Waiting
        onTriggered: {
            root.captureState = SimulatorMain.Capturing
            if (!root.contentItem.grabToImage(function(result) {
                if (!result.saveToFile(runtimeScreenshotPath))
                    console.warn("ktrmnl2: could not save " + runtimeScreenshotPath)
                root.captureState = SimulatorMain.Finished
                screenshotController.finish()
            })) {
                console.warn("ktrmnl2: could not capture the simulator window")
                root.captureState = SimulatorMain.Finished
                screenshotController.finish()
            }
        }
    }
}
