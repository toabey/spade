import theano, numpy
from theano import tensor as T

from hypernymy import HypernymModel
from preferences import PreferenceModel
from reconstruction import ReconstructionModel 

class EventAE(object):
	def __init__(self, num_args, vocab_size, ont_size, hyp_hidden_size, wc_hidden_sizes, cc_hidden_sizes, word_dim=50, concept_dim=50):
		numpy_rng = numpy.random.RandomState(12345)
		vocab_rep_range = 4 * numpy.sqrt(6. / (vocab_size + word_dim))
		init_vocab_rep = numpy.asarray(numpy_rng.uniform(low = -vocab_rep_range, high = vocab_rep_range, size=(vocab_size, word_dim)) )
		ont_rep_range = 4 * numpy.sqrt(6. / (ont_size + concept_dim))
		init_ont_rep = numpy.asarray(numpy_rng.uniform(low = -ont_rep_range, high = ont_rep_range, size=(ont_size, concept_dim)) )
		vocab_rep = theano.shared(value=init_vocab_rep, name='vocab_rep')
		ont_rep = theano.shared(value=init_ont_rep, name='ont_rep')
		self.enc_params = []
		self.hyp_model = HypernymModel('linlayer', hyp_hidden_size, vocab_rep, ont_rep)
		self.enc_params.extend(self.hyp_model.get_params())
		self.wc_pref_models = []
		self.cc_pref_models = []
		self.num_slots = num_args + 1 # +1 for the predicate
		self.num_args = num_args
		for i in range(self.num_slots):
			wc_pref_model = PreferenceModel('word_concept', 'linlayer', wc_hidden_sizes[i], ont_rep, vocab_rep)
			self.wc_pref_models.append(wc_pref_model)
			self.enc_params.extend(wc_pref_model.get_params())
	
		for i in range(num_args):
			cc_pref_model = PreferenceModel('concept_concept', 'linlayer', cc_hidden_sizes[i], ont_rep)
			self.cc_pref_models.append(cc_pref_model)
			self.enc_params.extend(cc_pref_model.get_params())
		self.rec_model = ReconstructionModel(ont_size, vocab_rep)
		self.rec_params = self.rec_model.get_params()
		
	def get_sym_encoder_energy(self, x, y):
		hsum = T.constant(0)
		for i in range(self.num_slots):
			hsum += self.hyp_model.get_symb_score(x[i], y[i])
		p_w_c_sum = T.constant(0)
		for i in range(self.num_slots):
			for j in range(self.num_slots):
				if i == j:
					continue
				p_w_c_sum += self.wc_pref_models[i].get_symb_score(x[i], y[j])
		p_c_c_sum = T.constant(0)
		for i in range(self.num_args):
			p_c_c_sum += self.cc_pref_models[i].get_symb_score(y[0], y[i])
		return hsum + p_w_c_sum + p_c_c_sum

	def get_sym_encoder_partition(self, x, y_s):
		partial_sums, _ = theano.scan(fn=lambda y, interm_sum, x_0: interm_sum + T.exp(self.get_sym_encoder_energy(x_0, y)), outputs_info=numpy.asarray(0.0, dtype='float64'), sequences=[y_s], non_sequences=x)
		encoder_partition = partial_sums[-1]
		return encoder_partition

	def get_sym_rec_prob(self, x, y):
		init_prob = T.constant(1.0, dtype='float64')
		partial_prods, _ = theano.scan(fn = lambda x_i, y_i, interm_prod: interm_prod * self.rec_model.get_sym_rec_prob(x_i, y_i), outputs_info=init_prob, sequences=[x, y])
		rec_prob = partial_prods[-1]
		return rec_prob
		
	def get_sym_posterior_num(self, x, y):
		enc_energy = self.get_sym_encoder_energy(x, y)
		rec_prob = self.get_sym_rec_prob(x, y)
		return T.exp(enc_energy) * rec_prob
			
	def get_sym_posterior_partition(self, x, y_s):
		partial_sums, _ = theano.scan(fn=lambda y, interm_sum, x_0: interm_sum + self.get_sym_posterior_num(x_0, y), outputs_info=numpy.asarray(0.0, dtype='float64'), sequences=[y_s], non_sequences=x)
		posterior_partition = partial_sums[-1]
		return posterior_partition

	def get_sym_complete_expectation(self, x, y_s):
		encoder_partition = self.get_sym_encoder_partition(x, y_s)
		posterior_partition = self.get_sym_posterior_partition(x, y_s)
		prod_fun = lambda y_0, interm_sum, x_0: interm_sum + \
				self.get_sym_posterior_num(x_0, y_0) * \
				( self.get_sym_encoder_energy(x_0, y_0) - T.log(encoder_partition) + \
					T.log(self.get_sym_rec_prob(x_0, y_0)) )
		partial_sums, _ = theano.scan(fn=prod_fun, outputs_info=numpy.asarray(0.0, dtype='float64'), sequences=[y_s], non_sequences=x)
		complete_expectation = partial_sums[-1] / posterior_partition
		return complete_expectation
		

