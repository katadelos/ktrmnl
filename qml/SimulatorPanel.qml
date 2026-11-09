import QtQuick 2.15

FocusScope {
    id: root

    property var controls
    property var displayBackend
    property var controller
    property var wifiBackend
    property var contentModel
    property var translator
    property bool firstRunActive: false
    enum Drawer { Closed, Open }
    enum Tab { Preview, Configuration }
    property int drawer: SimulatorPanel.Closed
    property int activeTab: SimulatorPanel.Preview
    readonly property bool open: drawer === SimulatorPanel.Open
    property string resolutionError: ""
    readonly property int panelWidth: Math.min(
        Math.round(420 * hostScale),
        Math.max(Math.round(300 * hostScale), Math.round(width * 0.54)),
        width - Math.round(20 * hostScale)
    )
    readonly property real hostScale: Math.max(0.86, Math.min(1.15, height / 700))
    readonly property color panelColor: "#f3f3ef"
    readonly property color cardColor: "#ffffff"
    readonly property color inkColor: "#171715"
    readonly property color secondaryColor: "#6b6b65"
    readonly property color lineColor: "#d4d4cd"
    readonly property color selectedColor: "#20201e"
    readonly property color selectedInk: "#ffffff"
    readonly property string headingFont: headingFontLoader.name
    readonly property string bodyFont: bodyFontLoader.name
    readonly property string cjkFont: cjkFontLoader.name
    signal pageRequested(string page)
    signal firstRunStateRequested(bool active)
    signal dismissed()

    function showPanel() {
        drawer = SimulatorPanel.Open
        forceActiveFocus()
    }

    function hidePanel() {
        drawer = SimulatorPanel.Closed
        dismissed()
    }

    function setResolution(width, height) {
        if (!controls.setDisplaySize(width, height)) {
            resolutionError = "Use a width and height between 64 and 4096 pixels."
            return
        }
        resolutionError = ""
        widthInput.text = String(displayBackend.nativeWidth)
        heightInput.text = String(displayBackend.nativeHeight)
    }

    function connectNetwork(network) {
        wifiBackend.connectNetwork(
            String(network.ssid), Boolean(network.secured) ? "simulator" : ""
        )
        controller.refreshDeviceStatus()
    }

    function openPage(page) {
        pageRequested(page)
        hidePanel()
    }

    function cycleLanguage(delta) {
        if (!translator || translator.languages.length <= 0) return
        var selected = 0
        for (var index = 0; index < translator.languages.length; index++) {
            if (String(translator.languages[index].code) === String(translator.language)) {
                selected = index
                break
            }
        }
        var next = (selected + delta + translator.languages.length)
                   % translator.languages.length
        translator.setLanguage(String(translator.languages[next].code), true)
    }

    FontLoader {
        id: headingFontLoader
        source: Qt.resolvedUrl("../assets/fonts/KTRMNLDINMittelschrift-Regular.otf")
    }

    FontLoader {
        id: bodyFontLoader
        source: Qt.resolvedUrl("../assets/fonts/NeueHaasDisplayRoman.ttf")
    }

    FontLoader {
        id: cjkFontLoader
        source: Qt.resolvedUrl("../assets/fonts/NotoSansCJK-Regular.ttc")
    }

    Keys.onEscapePressed: {
        if (root.open) {
            root.hidePanel()
            event.accepted = true
        }
    }

    Rectangle {
        id: launcher
        visible: !root.open
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Math.round(14 * root.hostScale)
        width: Math.round(138 * root.hostScale)
        height: Math.round(40 * root.hostScale)
        radius: height / 2
        color: launcherArea.pressed ? root.inkColor : root.panelColor
        border.color: root.inkColor
        border.width: 1

        Row {
            anchors.centerIn: parent
            spacing: Math.round(8 * root.hostScale)

            Text {
                text: "☰"
                color: launcherArea.pressed ? root.selectedInk : root.inkColor
                font.family: root.bodyFont
                font.pixelSize: Math.round(18 * root.hostScale)
            }

            Text {
                text: "Simulator"
                color: launcherArea.pressed ? root.selectedInk : root.inkColor
                font.family: root.headingFont
                font.pixelSize: Math.round(15 * root.hostScale)
            }
        }

        MouseArea {
            id: launcherArea
            anchors.fill: parent
            onClicked: root.showPanel()
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.open
        color: "#66000000"

        MouseArea {
            anchors.fill: parent
            onClicked: root.hidePanel()
        }
    }

    Rectangle {
        id: panel
        visible: root.open
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: Math.round(10 * root.hostScale)
        width: root.panelWidth
        radius: Math.round(18 * root.hostScale)
        color: root.panelColor
        border.color: root.inkColor
        border.width: 1
        clip: true

        MouseArea {
            anchors.fill: parent
        }

        Rectangle {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: Math.round(66 * root.hostScale)
            color: root.panelColor

            Text {
                anchors.left: parent.left
                anchors.leftMargin: Math.round(20 * root.hostScale)
                anchors.verticalCenter: parent.verticalCenter
                text: "Simulator controls"
                color: root.inkColor
                font.family: root.headingFont
                font.pixelSize: Math.round(23 * root.hostScale)
            }

            Rectangle {
                anchors.right: parent.right
                anchors.rightMargin: Math.round(14 * root.hostScale)
                anchors.verticalCenter: parent.verticalCenter
                width: Math.round(38 * root.hostScale)
                height: width
                radius: width / 2
                color: closeArea.pressed ? root.inkColor : root.cardColor
                border.color: root.lineColor
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "×"
                    color: closeArea.pressed ? root.selectedInk : root.inkColor
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(24 * root.hostScale)
                }

                MouseArea {
                    id: closeArea
                    anchors.fill: parent
                    onClicked: root.hidePanel()
                }
            }
        }

        Row {
            id: tabs
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: header.bottom
            anchors.leftMargin: Math.round(16 * root.hostScale)
            anchors.rightMargin: Math.round(16 * root.hostScale)
            height: Math.round(42 * root.hostScale)
            spacing: Math.round(6 * root.hostScale)

            Repeater {
                model: ["Controls", "All settings"]

                Rectangle {
                    width: (tabs.width - tabs.spacing) / 2
                    height: tabs.height
                    radius: Math.round(9 * root.hostScale)
                    color: root.activeTab === index ? root.selectedColor : root.cardColor
                    border.color: root.activeTab === index ? root.selectedColor : root.lineColor
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: root.activeTab === index ? root.selectedInk : root.inkColor
                        font.family: root.headingFont
                        font.pixelSize: Math.round(15 * root.hostScale)
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.activeTab = index
                    }
                }
            }
        }

        Flickable {
            id: controlsFlick
            visible: root.activeTab === SimulatorPanel.Preview
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tabs.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: Math.round(8 * root.hostScale)
            contentWidth: width
            contentHeight: controlsColumn.height + Math.round(24 * root.hostScale)
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: controlsColumn
                x: Math.round(16 * root.hostScale)
                width: controlsFlick.width - Math.round(32 * root.hostScale)
                spacing: Math.round(10 * root.hostScale)

                Text {
                    width: parent.width
                    text: "Preview"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Text {
                    width: parent.width
                    text: "Language"
                    color: root.secondaryColor
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(14 * root.hostScale)
                }

                Row {
                    id: languageChoices
                    width: parent.width
                    height: Math.round(39 * root.hostScale)
                    spacing: Math.round(6 * root.hostScale)

                    Rectangle {
                        width: Math.round(44 * root.hostScale)
                        height: languageChoices.height
                        radius: Math.round(8 * root.hostScale)
                        color: previousLanguageArea.pressed
                               ? root.inkColor : root.cardColor
                        border.color: root.lineColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "‹"
                            color: previousLanguageArea.pressed
                                   ? root.selectedInk : root.inkColor
                            font.family: root.bodyFont
                            font.pixelSize: Math.round(22 * root.hostScale)
                        }

                        MouseArea {
                            id: previousLanguageArea
                            anchors.fill: parent
                            onClicked: root.cycleLanguage(-1)
                        }
                    }

                    Rectangle {
                        width: languageChoices.width
                               - Math.round(88 * root.hostScale)
                               - languageChoices.spacing * 2
                        height: languageChoices.height
                        radius: Math.round(8 * root.hostScale)
                        color: root.selectedColor
                        border.color: root.selectedColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - Math.round(12 * root.hostScale)
                            text: root.translator ? root.translator.languageName : "English"
                            color: root.selectedInk
                            font.family: root.translator
                                         && (root.translator.language === "zh"
                                             || root.translator.language === "ja")
                                         ? root.cjkFont : root.headingFont
                            font.pixelSize: Math.round(14 * root.hostScale)
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        width: Math.round(44 * root.hostScale)
                        height: languageChoices.height
                        radius: Math.round(8 * root.hostScale)
                        color: nextLanguageArea.pressed
                               ? root.inkColor : root.cardColor
                        border.color: root.lineColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "›"
                            color: nextLanguageArea.pressed
                                   ? root.selectedInk : root.inkColor
                            font.family: root.bodyFont
                            font.pixelSize: Math.round(22 * root.hostScale)
                        }

                        MouseArea {
                            id: nextLanguageArea
                            anchors.fill: parent
                            onClicked: root.cycleLanguage(1)
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: "First-time setup"
                    color: root.secondaryColor
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(14 * root.hostScale)
                }

                Rectangle {
                    id: firstRunToggle
                    width: parent.width
                    height: Math.round(44 * root.hostScale)
                    radius: Math.round(8 * root.hostScale)
                    color: root.cardColor
                    border.color: root.firstRunActive ? root.inkColor : root.lineColor
                    border.width: root.firstRunActive ? 2 : 1

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Math.round(12 * root.hostScale)
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.firstRunActive ? "Setup flow active" : "Setup marked done"
                        color: root.inkColor
                        font.family: root.headingFont
                        font.pixelSize: Math.round(14 * root.hostScale)
                    }

                    Rectangle {
                        id: firstRunSwitch
                        anchors.right: parent.right
                        anchors.rightMargin: Math.round(11 * root.hostScale)
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(44 * root.hostScale)
                        height: Math.round(24 * root.hostScale)
                        radius: height / 2
                        color: root.firstRunActive ? root.inkColor : root.lineColor

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            x: root.firstRunActive
                               ? parent.width - width - Math.round(3 * root.hostScale)
                               : Math.round(3 * root.hostScale)
                            width: Math.round(18 * root.hostScale)
                            height: width
                            radius: width / 2
                            color: root.cardColor
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.firstRunStateRequested(!root.firstRunActive)
                    }
                }

                Text {
                    width: parent.width
                    text: "Resolution  ·  " + displayBackend.logicalWidth + " × "
                          + displayBackend.logicalHeight + " logical pixels  ·  UI profile "
                          + controls.activeUiProfile
                    color: root.secondaryColor
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(14 * root.hostScale)
                }

                Flow {
                    id: resolutionPresets
                    width: parent.width
                    height: childrenRect.height
                    spacing: Math.round(7 * root.hostScale)

                    Repeater {
                        model: [
                            {"label": "K4  600 × 800", "width": 600, "height": 800},
                            {"label": "PW  758 × 1024", "width": 758, "height": 1024},
                            {"label": "HD  1072 × 1448", "width": 1072, "height": 1448}
                        ]

                        Rectangle {
                            readonly property bool selected: displayBackend.nativeWidth === modelData.width
                                                             && displayBackend.nativeHeight === modelData.height
                            width: (resolutionPresets.width - resolutionPresets.spacing) / 2
                            height: Math.round(39 * root.hostScale)
                            radius: Math.round(8 * root.hostScale)
                            color: selected ? root.selectedColor : root.cardColor
                            border.color: selected ? root.selectedColor : root.lineColor
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData.label
                                color: parent.selected ? root.selectedInk : root.inkColor
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(14 * root.hostScale)
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.setResolution(modelData.width, modelData.height)
                            }
                        }
                    }
                }

                Row {
                    id: customResolution
                    width: parent.width
                    height: Math.round(42 * root.hostScale)
                    spacing: Math.round(7 * root.hostScale)

                    Rectangle {
                        width: (customResolution.width - applyResolution.width
                                - customResolution.spacing * 3) / 2
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: root.cardColor
                        border.color: widthInput.activeFocus ? root.inkColor : root.lineColor
                        border.width: widthInput.activeFocus ? 2 : 1

                        TextInput {
                            id: widthInput
                            anchors.fill: parent
                            anchors.leftMargin: Math.round(11 * root.hostScale)
                            anchors.rightMargin: Math.round(11 * root.hostScale)
                            verticalAlignment: TextInput.AlignVCenter
                            text: String(displayBackend.nativeWidth)
                            color: root.inkColor
                            selectionColor: root.inkColor
                            selectedTextColor: root.selectedInk
                            font.family: root.bodyFont
                            font.pixelSize: Math.round(15 * root.hostScale)
                            selectByMouse: true
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: IntValidator { bottom: 64; top: 4096 }
                            onAccepted: root.setResolution(parseInt(text), parseInt(heightInput.text))
                        }
                    }

                    Text {
                        height: parent.height
                        verticalAlignment: Text.AlignVCenter
                        text: "×"
                        color: root.secondaryColor
                        font.family: root.bodyFont
                        font.pixelSize: Math.round(17 * root.hostScale)
                    }

                    Rectangle {
                        width: (customResolution.width - applyResolution.width
                                - customResolution.spacing * 3) / 2
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: root.cardColor
                        border.color: heightInput.activeFocus ? root.inkColor : root.lineColor
                        border.width: heightInput.activeFocus ? 2 : 1

                        TextInput {
                            id: heightInput
                            anchors.fill: parent
                            anchors.leftMargin: Math.round(11 * root.hostScale)
                            anchors.rightMargin: Math.round(11 * root.hostScale)
                            verticalAlignment: TextInput.AlignVCenter
                            text: String(displayBackend.nativeHeight)
                            color: root.inkColor
                            selectionColor: root.inkColor
                            selectedTextColor: root.selectedInk
                            font.family: root.bodyFont
                            font.pixelSize: Math.round(15 * root.hostScale)
                            selectByMouse: true
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: IntValidator { bottom: 64; top: 4096 }
                            onAccepted: root.setResolution(parseInt(widthInput.text), parseInt(text))
                        }
                    }

                    Rectangle {
                        id: applyResolution
                        width: Math.round(62 * root.hostScale)
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: applyResolutionArea.pressed ? root.inkColor : root.cardColor
                        border.color: root.inkColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "Apply"
                            color: applyResolutionArea.pressed ? root.selectedInk : root.inkColor
                            font.family: root.headingFont
                            font.pixelSize: Math.round(14 * root.hostScale)
                        }

                        MouseArea {
                            id: applyResolutionArea
                            anchors.fill: parent
                            onClicked: root.setResolution(
                                parseInt(widthInput.text), parseInt(heightInput.text)
                            )
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: root.resolutionError.length > 0
                    text: root.resolutionError
                    color: "#9f2921"
                    wrapMode: Text.Wrap
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(13 * root.hostScale)
                }

                Connections {
                    target: displayBackend
                    function onGeometryChanged() {
                        if (!widthInput.activeFocus)
                            widthInput.text = String(displayBackend.nativeWidth)
                        if (!heightInput.activeFocus)
                            heightInput.text = String(displayBackend.nativeHeight)
                    }
                }

                SimulatorScaleControl {
                    width: parent.width
                    title: "Text size"
                    hint: "50–500% · saved for this resolution"
                    currentValue: controls.textScale
                    minimumValue: 0.5
                    maximumValue: 5.0
                    step: 0.1
                    defaultValue: controls.defaultTextScale
                    uiScale: root.hostScale
                    cardColor: root.cardColor
                    inkColor: root.inkColor
                    secondaryColor: root.secondaryColor
                    lineColor: root.lineColor
                    selectedInk: root.selectedInk
                    headingFont: root.headingFont
                    bodyFont: root.bodyFont
                    onValueRequested: function(value) { controls.setTextScale(value) }
                }

                SimulatorScaleControl {
                    width: parent.width
                    title: "Menu row height"
                    hint: "50–400% · saved for this resolution"
                    currentValue: controls.rowHeightScale
                    minimumValue: 0.5
                    maximumValue: 4.0
                    step: 0.1
                    defaultValue: controls.defaultRowHeightScale
                    uiScale: root.hostScale
                    cardColor: root.cardColor
                    inkColor: root.inkColor
                    secondaryColor: root.secondaryColor
                    lineColor: root.lineColor
                    selectedInk: root.selectedInk
                    headingFont: root.headingFont
                    bodyFont: root.bodyFont
                    onValueRequested: function(value) { controls.setRowHeightScale(value) }
                }

                SimulatorScaleControl {
                    width: parent.width
                    title: "Keyboard height"
                    hint: "25–75% of screen · saved for this resolution"
                    currentValue: controls.keyboardHeightRatio
                    minimumValue: 0.25
                    maximumValue: 0.75
                    step: 0.05
                    defaultValue: controls.defaultKeyboardHeightRatio
                    uiScale: root.hostScale
                    cardColor: root.cardColor
                    inkColor: root.inkColor
                    secondaryColor: root.secondaryColor
                    lineColor: root.lineColor
                    selectedInk: root.selectedInk
                    headingFont: root.headingFont
                    bodyFont: root.bodyFont
                    onValueRequested: function(value) {
                        controls.setKeyboardHeightRatio(value)
                    }
                }

                Text {
                    width: parent.width
                    topPadding: Math.round(4 * root.hostScale)
                    text: "Rotation"
                    color: root.secondaryColor
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(14 * root.hostScale)
                }

                Row {
                    id: rotationChoices
                    width: parent.width
                    height: Math.round(40 * root.hostScale)
                    spacing: Math.round(6 * root.hostScale)

                    Repeater {
                        model: [0, 90, 180, 270]

                        Rectangle {
                            readonly property bool selected: controller.rotation === modelData
                            width: (rotationChoices.width - rotationChoices.spacing * 3) / 4
                            height: rotationChoices.height
                            radius: Math.round(8 * root.hostScale)
                            color: selected ? root.selectedColor : root.cardColor
                            border.color: selected ? root.selectedColor : root.lineColor
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData + "°"
                                color: parent.selected ? root.selectedInk : root.inkColor
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(14 * root.hostScale)
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: controller.applySetting("setting-rotation", modelData)
                            }
                        }
                    }
                }

                Row {
                    id: displayActions
                    width: parent.width
                    height: Math.round(42 * root.hostScale)
                    spacing: Math.round(7 * root.hostScale)

                    Rectangle {
                        width: (displayActions.width - displayActions.spacing) / 2
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: controller.darkMode ? root.selectedColor : root.cardColor
                        border.color: controller.darkMode ? root.selectedColor : root.lineColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: controller.darkMode ? "Dark mode on" : "Dark mode off"
                            color: controller.darkMode ? root.selectedInk : root.inkColor
                            font.family: root.headingFont
                            font.pixelSize: Math.round(14 * root.hostScale)
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: controller.toggleDarkMode()
                        }
                    }

                    Rectangle {
                        width: (displayActions.width - displayActions.spacing) / 2
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: refreshArea.pressed ? root.inkColor : root.cardColor
                        border.color: root.lineColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "Refresh content"
                            color: refreshArea.pressed ? root.selectedInk : root.inkColor
                            font.family: root.headingFont
                            font.pixelSize: Math.round(14 * root.hostScale)
                        }

                        MouseArea {
                            id: refreshArea
                            anchors.fill: parent
                            onClicked: controller.refresh()
                        }
                    }
                }

                Rectangle {
                    width: parent.width
                    height: 1
                    color: root.lineColor
                }

                Text {
                    width: parent.width
                    text: "Wi-Fi"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Text {
                    width: parent.width
                    text: (wifiBackend.connected
                             ? "Connected · " + wifiBackend.connectedSsid
                             : (wifiBackend.radioPowered ? "Radio on · not connected" : "Radio off"))
                    color: root.secondaryColor
                    elide: Text.ElideRight
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(14 * root.hostScale)
                }

                Row {
                    id: wifiActions
                    width: parent.width
                    height: Math.round(42 * root.hostScale)
                    spacing: Math.round(7 * root.hostScale)

                    Rectangle {
                        width: wifiActions.width
                        height: parent.height
                        radius: Math.round(8 * root.hostScale)
                        color: wifiBackend.radioPowered ? root.selectedColor : root.cardColor
                        border.color: wifiBackend.radioPowered ? root.selectedColor : root.lineColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: wifiBackend.radioPowered ? "Radio on" : "Radio off"
                            color: wifiBackend.radioPowered ? root.selectedInk : root.inkColor
                            font.family: root.headingFont
                            font.pixelSize: Math.round(14 * root.hostScale)
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: controller.toggleWifi()
                        }
                    }

                }

                Column {
                    width: parent.width
                    height: childrenRect.height
                    spacing: Math.round(6 * root.hostScale)

                    Repeater {
                        model: wifiBackend.networks

                        Rectangle {
                            width: controlsColumn.width
                            height: Math.round(46 * root.hostScale)
                            radius: Math.round(8 * root.hostScale)
                            color: Boolean(modelData.connected) ? root.selectedColor : root.cardColor
                            border.color: Boolean(modelData.connected) ? root.selectedColor : root.lineColor
                            border.width: 1

                            Text {
                                anchors.left: parent.left
                                anchors.right: networkMeta.left
                                anchors.leftMargin: Math.round(12 * root.hostScale)
                                anchors.rightMargin: Math.round(8 * root.hostScale)
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.ssid
                                color: Boolean(modelData.connected) ? root.selectedInk : root.inkColor
                                elide: Text.ElideRight
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(15 * root.hostScale)
                            }

                            Text {
                                id: networkMeta
                                anchors.right: parent.right
                                anchors.rightMargin: Math.round(12 * root.hostScale)
                                anchors.verticalCenter: parent.verticalCenter
                                text: Boolean(modelData.connected) ? "Connected" : modelData.security
                                color: Boolean(modelData.connected) ? root.selectedInk : root.secondaryColor
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(13 * root.hostScale)
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.connectNetwork(modelData)
                            }
                        }
                    }
                }

                Rectangle {
                    width: parent.width
                    height: 1
                    color: root.lineColor
                }

                Text {
                    width: parent.width
                    text: "Content source"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Flow {
                    id: modeChoices
                    width: parent.width
                    height: childrenRect.height
                    spacing: Math.round(7 * root.hostScale)

                    Repeater {
                        model: [
                            {"label": "TRMNL", "value": "trmnl"},
                            {"label": "Interrupt", "value": "interrupt"},
                            {"label": "Local images", "value": "local_images"},
                            {"label": "HTTP push", "value": "http_push"}
                        ]

                        Rectangle {
                            readonly property bool selected: contentModel.mode === modelData.value
                            width: (modeChoices.width - modeChoices.spacing) / 2
                            height: Math.round(40 * root.hostScale)
                            radius: Math.round(8 * root.hostScale)
                            color: selected ? root.selectedColor : root.cardColor
                            border.color: selected ? root.selectedColor : root.lineColor
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData.label
                                color: parent.selected ? root.selectedInk : root.inkColor
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(14 * root.hostScale)
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: controller.setMode(modelData.value)
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    topPadding: Math.round(6 * root.hostScale)
                    text: "Open a page"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Flow {
                    id: pageChoices
                    width: parent.width
                    height: childrenRect.height
                    spacing: Math.round(7 * root.hostScale)

                    Repeater {
                        model: [
                            {"label": "Content", "page": "content"},
                            {"label": "Display", "page": "display"},
                            {"label": "Network", "page": "wifi-settings"},
                            {"label": "System", "page": "system"},
                            {"label": "Status", "page": "status"}
                        ]

                        Rectangle {
                            width: (pageChoices.width - pageChoices.spacing) / 2
                            height: Math.round(40 * root.hostScale)
                            radius: Math.round(8 * root.hostScale)
                            color: pageArea.pressed ? root.inkColor : root.cardColor
                            border.color: root.lineColor
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData.label
                                color: pageArea.pressed ? root.selectedInk : root.inkColor
                                font.family: root.headingFont
                                font.pixelSize: Math.round(14 * root.hostScale)
                            }

                            MouseArea {
                                id: pageArea
                                anchors.fill: parent
                                onClicked: root.openPage(modelData.page)
                            }
                        }
                    }
                }
            }
        }

        Flickable {
            id: settingsFlick
            visible: root.activeTab === SimulatorPanel.Configuration
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tabs.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: Math.round(8 * root.hostScale)
            contentWidth: width
            contentHeight: settingsColumn.height + Math.round(24 * root.hostScale)
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: settingsColumn
                x: Math.round(16 * root.hostScale)
                width: settingsFlick.width - Math.round(32 * root.hostScale)
                spacing: Math.round(8 * root.hostScale)

                Text {
                    width: parent.width
                    text: "Live preview"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Rectangle {
                    width: parent.width
                    height: Math.round(62 * root.hostScale)
                    radius: Math.round(9 * root.hostScale)
                    color: root.cardColor
                    border.color: root.lineColor
                    border.width: 1

                    Text {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.leftMargin: Math.round(12 * root.hostScale)
                        anchors.topMargin: Math.round(9 * root.hostScale)
                        text: "Screen"
                        color: root.secondaryColor
                        font.family: root.bodyFont
                        font.pixelSize: Math.round(13 * root.hostScale)
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: Math.round(12 * root.hostScale)
                        anchors.rightMargin: Math.round(12 * root.hostScale)
                        anchors.bottomMargin: Math.round(8 * root.hostScale)
                        text: displayBackend.logicalWidth + " × " + displayBackend.logicalHeight
                              + "  ·  text " + Math.round(controls.textScale * 100) + "%"
                              + "  ·  rows " + Math.round(controls.rowHeightScale * 100) + "%"
                              + "  ·  keyboard "
                              + Math.round(controls.keyboardHeightRatio * 100) + "%"
                        color: root.inkColor
                        font.family: root.bodyFont
                        font.pixelSize: Math.round(15 * root.hostScale)
                    }
                }

                Rectangle {
                    width: parent.width
                    height: Math.round(62 * root.hostScale)
                    radius: Math.round(9 * root.hostScale)
                    color: root.cardColor
                    border.color: root.lineColor
                    border.width: 1

                    Text {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.leftMargin: Math.round(12 * root.hostScale)
                        anchors.topMargin: Math.round(9 * root.hostScale)
                        text: "Wi-Fi"
                        color: root.secondaryColor
                        font.family: root.bodyFont
                        font.pixelSize: Math.round(13 * root.hostScale)
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: Math.round(12 * root.hostScale)
                        anchors.rightMargin: Math.round(12 * root.hostScale)
                        anchors.bottomMargin: Math.round(8 * root.hostScale)
                        text: (wifiBackend.connected ? wifiBackend.connectedSsid
                                 : (wifiBackend.radioPowered ? "On · not connected" : "Off"))
                        color: root.inkColor
                        elide: Text.ElideMiddle
                        font.family: root.bodyFont
                        font.pixelSize: Math.round(15 * root.hostScale)
                    }
                }

                Text {
                    width: parent.width
                    topPadding: Math.round(8 * root.hostScale)
                    text: "Saved settings"
                    color: root.inkColor
                    font.family: root.headingFont
                    font.pixelSize: Math.round(20 * root.hostScale)
                }

                Column {
                    width: parent.width
                    height: childrenRect.height
                    spacing: Math.round(6 * root.hostScale)

                    Repeater {
                        model: controls.settings

                        Rectangle {
                            width: settingsColumn.width
                            height: Math.round(62 * root.hostScale)
                            radius: Math.round(9 * root.hostScale)
                            color: root.cardColor
                            border.color: root.lineColor
                            border.width: 1

                            Text {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.leftMargin: Math.round(12 * root.hostScale)
                                anchors.topMargin: Math.round(8 * root.hostScale)
                                text: modelData.label
                                color: root.secondaryColor
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(13 * root.hostScale)
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: Math.round(12 * root.hostScale)
                                anchors.rightMargin: Math.round(12 * root.hostScale)
                                anchors.bottomMargin: Math.round(8 * root.hostScale)
                                text: modelData.value
                                color: root.inkColor
                                elide: Text.ElideMiddle
                                font.family: root.bodyFont
                                font.pixelSize: Math.round(15 * root.hostScale)
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    topPadding: Math.round(6 * root.hostScale)
                    text: "Config file\n" + controls.configPath
                    color: root.secondaryColor
                    wrapMode: Text.WrapAnywhere
                    font.family: root.bodyFont
                    font.pixelSize: Math.round(12 * root.hostScale)
                }
            }
        }
    }
}
