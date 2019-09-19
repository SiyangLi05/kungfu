
import { initDB } from '@/base';
//@ts-ignore
import { version } from '../package.json';
import { addAccountStrategy } from '@/commanders/add';
import { listAccountsStrategys } from '@/commanders/list';
import { removeAccountStrategy } from '@/commanders/remove';
import { updateAccountStrategy } from '@/commanders/update';
import { switchMdSource } from '@/commanders/switchMdSsource';
import { monitPrompt } from '@/components/index';
import { delaySeconds } from '__gUtils/busiUtils';
import { startLedger, startMaster, killExtra } from '__gUtils/processUtils';
import { removeFilesInFolder } from '__gUtils/fileUtils';
import { logger } from '__gUtils/logUtils';
import { LEDGER_DIR, LIVE_TRADING_DB_DIR, LOG_DIR, BASE_DB_DIR, KF_HOME } from '__gConfig/pathConfig';

const program = require('commander');

program
    .version(version)
    .option('-l --list', 'list target process to monit');

program
    .command('monit [options]')
    .description('monitor target process')
    .action((type: any, commander: any) => {
        const list = commander.parent.list
        return monitPrompt(!!list)
    })

//list
program
    .command('list')
    .description('list accounts and strategies')
    .action(() => {
        return listAccountsStrategys()
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0));
    })

//add
program
    .command('add <account|strategy>')
    .description('add a account or strategy')
    .action((type: string) => {
        return addAccountStrategy(type)
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0));
    })

//update
program
    .command('update')
    .description('update a account or strategy')
    .action(() => {
        return updateAccountStrategy()
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0));
    })

//remove
program
    .command('remove')
    .description('remove a account or strategy')
    .action(() => {
        return removeAccountStrategy()
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0));
    })

program
    .command('switchMd')
    .description('switch md source')
    .action(() => {
        return switchMdSource()
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0));
    })

program
    .command('shutdown')
    .description('shutdown all kungfu processes')
    .action(() => {
        return killExtra()
        .then(() => console.log('Shutdown kungfu successfully!'))
        .finally(() => process.exit(0))
    })

program
    .command('clearLog')
    .description('clear all logs (Tips: should do it often)')
    .action(() => {
        return removeFilesInFolder(LOG_DIR)
            .then(() => console.log('Clear all logs successfully!'))
            .catch((err: Error) => console.error(err))
            .finally(() => process.exit(0))
    })

program
    .command('showDir <home|log|ledger|base>')
    .description('show the dir path of home or log or ledger or base')
    .action((target: string) => {
        switch (target) {
            case 'home':
                console.log(KF_HOME)
                break;
            case 'log':
                console.log(LOG_DIR)
                break;
            case 'ledger':
                console.log(LIVE_TRADING_DB_DIR)
                break;
            case 'base':
                console.log(BASE_DB_DIR)
                break;
        }
        process.exit(0)
    })

if (process.env.NODE_ENV !== 'production') {
    program.parse(process.argv)
} else {
    //@ts-ignore
    program.parse([null].concat(process.argv))
}

initDB()

startMaster(false)
    .catch(() => {})
    .finally(() => {
        delaySeconds(1000)
        .then(() => startLedger(false))
        .catch(() => {})
    })
