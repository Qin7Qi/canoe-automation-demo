pipeline {
    agent { label 'canoe-agent' }

    environment {
        PROJECT_DIR = ''
        PYTHON      = 'python'
    }

    options {
        timeout(time: 1, unit: 'HOURS')
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    triggers {
        githubPush()
    }

    stages {
        stage('Install Dependencies') {
            steps {
                bat "${PYTHON} -m pip install -r pytests/requirements.txt"
            }
        }

        //  测试
        stage('Run Tests') {
            steps {
                // 关键：先 cd 到工程根目录，main.py 的相对路径才正确
                bat "${PYTHON} pytests\\test.py"
            }
        }

    //     //  CANoe自动化测试启动
    //     stage('Run CANoe Tests') {
    //         steps {
    //             // 关键：先 cd 到工程根目录，main.py 的相对路径才正确
    //             bat "cd ${PROJECT_DIR} && ${PYTHON} pytests\\main.py"
    //         }
    //     }

    //     stage('Convert Reports to JUnit') {
    //         steps {
    //             bat "cd ${PROJECT_DIR} && ${PYTHON} pytests\\tools\\convert_reports.py"
    //         }
    //     }
    }

    // post {
    //     always {
    //         // 发布 JUnit 报告（趋势图 + 用例详情）
    //         junit "${PROJECT_DIR}/reports/*_junit.xml"
    //         // 归档 CANoe 原生报告和日志
    //         archiveArtifacts artifacts: "${PROJECT_DIR}/reports/**", fingerprint: true
    //     }
    //     failure {
    //         echo 'CANoe 测试失败，请查看测试报告和 CANoe 日志'
    //     }
    // }
}