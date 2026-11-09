import QtQuick 2.15

Rectangle {
    id: root
    objectName: "languageSelection"
    property var theme
    property var translator
    property int selectedIndex: 0
    property bool onboarding: false
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    readonly property int languageCount: translator ? translator.languages.length : 0
    readonly property string previewLanguage: languageCount > 0
        ? String(translator.languages[Math.max(0, Math.min(selectedIndex, languageCount - 1))].code)
        : "en"
    signal selectionRequested(int index)
    signal languageRequested(string language)
    signal backRequested()

    color: theme.paper

    function translatedText(key) {
        var language = activeLanguage
        return translator.text(String(key))
    }

    PageHeader {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        backVisible: !root.onboarding
        onBackRequested: root.backRequested()
        title: root.onboarding
            ? root.translator.textFor(root.previewLanguage, "onboarding.language_welcome")
            : root.translator.textFor(root.previewLanguage, "language.title")
    }

    Row {
        id: languageColumns
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.compactMargin
        height: Math.min(
                    root.theme.rowHeight * 4,
                    root.height - header.height - root.theme.compactMargin
                    - root.theme.outerMargin
                )
        spacing: root.theme.compactMargin

        Repeater {
            model: 3

            Item {
                id: languageColumn
                readonly property int columnIndex: index
                width: (languageColumns.width - languageColumns.spacing * 2) / 3
                height: languageColumns.height

                Column {
                    anchors.fill: parent

                    Repeater {
                        model: 4

                        Rectangle {
                            id: languageCell
                            readonly property int languageIndex:
                                languageColumn.columnIndex * 4 + index
                            readonly property var languageData:
                                root.translator.languages[languageIndex]
                            readonly property bool currentLanguage:
                                String(languageData.code) === root.activeLanguage
                            readonly property bool selected: languagePress.highlighted
                                || (root.theme.navigationFocus && languageIndex === root.selectedIndex)
                            width: parent.width
                            height: languageColumns.height / 4
                            color: selected ? root.theme.ink : root.theme.paper

                            Text {
                                anchors.left: parent.left
                                anchors.right: currentLanguageMark.left
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: root.theme.compactMargin
                                anchors.rightMargin: Math.round(6 * root.theme.scale)
                                text: parent.languageData.name
                                color: parent.selected ? root.theme.paper : root.theme.ink
                                font.family: languageCell.languageData.code === "zh"
                                             || languageCell.languageData.code === "ja"
                                             ? root.theme.cjkFontLoader.name
                                             : root.theme.displayFontLoader.name
                                font.pixelSize: root.theme.controlSize
                                horizontalAlignment: Text.AlignLeft
                                elide: Text.ElideRight
                            }

                            RadioIndicator {
                                id: currentLanguageMark
                                anchors.right: parent.right
                                anchors.rightMargin: root.theme.compactMargin
                                anchors.verticalCenter: parent.verticalCenter
                                theme: root.theme
                                width: Math.round(18 * root.theme.scale)
                                checked: true
                                inverted: languageCell.selected
                                visible: languageCell.currentLanguage
                            }

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 1
                                color: root.theme.ink
                                visible: index < 3
                            }

                            PressArea {
                                id: languagePress
                                anchors.fill: parent
                                theme: root.theme
                                actionData: ({index: languageCell.languageIndex,
                                              code: String(languageCell.languageData.code)})
                                onTriggered: function(data) {
                                    root.selectionRequested(data.index)
                                    root.languageRequested(data.code)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
