import json
import logging
from os.path import exists
import requests
import sys
import subprocess
import toml
import urllib

class EvidenceChecker():
    """
    In order to use this class you will need to have the binaries listed in
    the config file available in your path.
    Every time there are new evidence entries, the evidence file gets updated.
    
    checker = EvidenceChecker('config.toml')
    print(checker.get_evidence_updates())
    """
    def __init__(self, config_file: str):
        with open(config_file, "r") as config_toml:
            self.config = toml.load(config_toml)
        try:
            self.EVIDENCE_BINARY=str(self.config['evidence_binary'])
            self.EVIDENCE_FILENAME=str(self.config['evidence_filename'])
            self.RPC_URL=str(self.config['chains']['cosmoshub']['rpc'])
            self.API_URL=str(self.config['chains']['cosmoshub']['api'])
        except KeyError as key_err:
            logging.critical('Key could not be found: %s', key_err)
            sys.exit()
        
        self.load_evidence()
        logging.info('Evidence checker loaded.')

    def empty_evidence(self):
        """
        Returns a chains dict with an empty evidence list.
        """
        self.chains=[]
        for chain, chain_data in self.config["chains"].items():
            self.chains.append(
                {
                    "chain_id": chain_data["chain_id"],
                    "api": chain_data["api"],
                    "rpc": chain_data["rpc"],
                    "binary": chain_data["binary"],
                    "evidence": [],
                    "evidence_id": []
                }
            )

    def load_evidence(self):
        """
        Reads evidence file JSON
        If it is empty or doesn't exists, it returns a dict with an empty evidence list.
        """
        if exists(self.EVIDENCE_FILENAME):
            with open(self.EVIDENCE_FILENAME, "r") as evidence_file:
                try:
                    self.chains=json.load(evidence_file)
                except:
                    self.empty_evidence()
        else:
            logging.info("Creating evidence file...")
            with open(self.EVIDENCE_FILENAME, "w") as evidence_file:
                self.empty_evidence()

    def query_evidence(self, chain: dict):
        """
        Queries the RPC endpoint, if it finds new evidence entries:
        - Updates the chain dict
        - Adds the deltas to the returned list
        """
        new_evidence = False
        deltas=[]
        result = subprocess.run(
            [
                self.EVIDENCE_BINARY,
                "q",
                "evidence",
                f"--node={chain['rpc']}",
                "--output=json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(result.stdout)["evidence"]
        
    def collect_rpc_validators(self, urlRPC, height: int=0):
        """
        Collects validators info at the latest block height
        - Address in bytes format
        - pubkey
        - voting power
        - proposer priority
        """
        page = 1
        if height > 0:
            response = requests.get(f"{urlRPC}/validators?page={page}&height={height}").json()['result']
        else:
            response = requests.get(f"{urlRPC}/validators?page={page}").json()['result']
        val_count = int(response['count'])
        total = int(response['total'])
        rpc_vals = response['validators']

        while val_count < total:
            page += 1
            if height > 0:
                response = requests.get(f"{urlRPC}/validators?page={page}&height={height}").json()['result']
            else:
                response = requests.get(f"{urlRPC}/validators?page={page}").json()['result']
            val_count += int(response['count'])
            rpc_vals.extend(response['validators'])
        return rpc_vals

    def collect_api_validators(self, urlAPI, height: int=0):
        """
        Collects the validators info at the specified height
        - operator address in cosmosvaloper format
        - consensus pubkey
        - jailed status
        - tokens
        - delegator shares
        - moniker
        - and more
        """
        if height > 0:
            response = requests.get(f"{urlAPI}/cosmos/staking/v1beta1/validators",
                            headers={'x-cosmos-block-height':f'{height}'}).json()
        else:
            response = requests.get(f"{urlAPI}/cosmos/staking/v1beta1/validators").json()
        total = int(response['pagination']['total'])
        api_vals = response['validators']
        next_key = response['pagination']['next_key']
        while next_key:
            response = requests.get(f'{urlAPI}/cosmos/staking/v1beta1/validators?pagination.key='
                       f'{urllib.parse.quote(next_key)}',
                       headers={'x-cosmos-block-height':f'{height}'}).json()
            api_vals.extend(response['validators'])
            next_key = response['pagination']['next_key']
        return api_vals

    def parse_key(self, binary: str, address: str, format: str):
        """
        Returns a hex address given a prefixed key (e.g. cosmosvalcons*).
        """
        result = subprocess.run(
            [
                binary,
                'keys',
                'parse',
                address,
                '--output=json',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(result.stdout)[format]

    def parse_address(self, binary: str, address: str, format: int):
        """
        Returns the specified format given a hex address to parse.
        """
        result = subprocess.run(
            [
                binary,
                'keys',
                'parse',
                address,
                '--output=json',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(result.stdout)['formats'][format]

    def key_assigned(self, chain_id: str, address: str):
        """
        Returns:
        - the provider consensus address if a key was assigned
        - an empty string if no key was assigned.
        """
        result = subprocess.run(
            [
                'gaiad',
                'q',
                'provider',
                'validator-provider-key',
                chain_id,
                address,
                '--output=json',
                f'--node={self.RPC_URL}',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(result.stdout)['provider_address']

    def hex_address_to_moniker(self, address: str):
        """
        Queries the RPC and API endpoints to return the public key
        and moniker given a consensus hex address.
        """
        pubkey = ''
        moniker = ''
        # Collect rpc vals for address and pubkey info
        rpc_vals = self.collect_rpc_validators(self.RPC_URL)
        for val in rpc_vals:
            if val['address'] == address:
                pubkey=val['pub_key']['value']
                break
        api_vals = self.collect_api_validators(self.API_URL)
        for val in api_vals:
            if val['consensus_pubkey']['key'] == pubkey:
                moniker=val['description']['moniker']
                break
        return pubkey, moniker

    def identify_addresses(self, eqs: list, chain: dict):
        """
        Add hex address and moniker to consensus addresses
        """
        identified = [d.copy() for d in eqs]
        for eq in identified:
            consumer_consensus=eq['consensus_address']
            consumer_hex=self.parse_key(chain['binary'], consumer_consensus, 'bytes')
            provider_consensus_check=self.parse_address('gaiad',consumer_hex,4)
            # Check if there is a key assigned to this address
            provider_addr = self.key_assigned(chain['chain_id'], provider_consensus_check)
            if not provider_addr:
                provider_addr = provider_consensus_check
            provider_hex = self.parse_key('gaiad',provider_addr,'bytes')
            pubkey, moniker = self.hex_address_to_moniker(provider_hex)
            eq['pubkey'] = pubkey
            eq['moniker'] = moniker
        return identified

    def get_evidence_updates(self):
        """
        Updates the equivocation and equivocation_id fields.
        """
        updates=[]
        for chain in self.chains:
            if chain['chain_id'] == 'cosmoshub-4':
                continue
            logging.info(f'Collecting evidence for {chain["chain_id"]}...')
            latest_evidence = self.query_evidence(chain)
            if chain["evidence"] != latest_evidence:
                deltas = self.identify_addresses([eq for eq in latest_evidence if eq not in chain["evidence"]], chain)
                chain["evidence"] = latest_evidence
                chain["evidence_id"] = self.identify_addresses(latest_evidence, chain)
                with open(self.EVIDENCE_FILENAME, "w") as evidence_file:
                    json.dump(self.chains, evidence_file, indent=4)
                    message = f'New equivocations recorded for {chain["chain_id"]}:\n{deltas}'
                    updates.append({'chain_id': chain['chain_id'],
                                    'updates':deltas})
            else:
                message = f'No new equivocations recorded for {chain["chain_id"]}.'
            logging.info(message)
        return updates
